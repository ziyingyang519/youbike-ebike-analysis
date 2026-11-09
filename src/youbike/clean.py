"""Load and clean YouBike 2.0 rental records.

Raw columns (confirmed from the 2025-08 to 2026-07 files):
    rent_time, rent_station, return_time, return_station, rent, bike_type, infodate
The 2025-08 to 2026-02 files have no header row but use the same column order.

Notes
-----
- rent_time / return_time are truncated to the hour (e.g. 17:00:00),
  so only the hour is kept.
- `rent` is the ride duration as HH:MM:SS, precise to the second.
- bike_type is '電輔車' (e-bike) or '一般車' (regular bike).
- One month is about 7-8 million rows (~0.5-0.9 GB of CSV), so files are
  read in chunks and only the needed columns are kept, with compact dtypes.

Cleaning rules (defaults, based on the 2026-03 file)
---------------------------------------------------
- Drop rows with a missing time, station, duration or bike type.
- Drop rides longer than 240 minutes (0.09% of rides; above the 99.9th
  percentile for both bike types). These are likely bikes that were not
  returned properly.
- Drop same-station rides shorter than 1 minute (0.1% of rides). These are
  likely failed rentals where the bike was put straight back.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.api.types import union_categoricals

RAW_COLUMNS = [
    "rent_time", "rent_station", "return_time", "return_station",
    "rent", "bike_type", "infodate",
]
BIKE_TYPE_MAP = {"電輔車": "ebike", "一般車": "regular"}
STATION_PREFIX = "YouBike2.0_"

DEFAULT_MAX_DURATION_MIN = 240
DEFAULT_MIN_SAME_STATION_MIN = 1
DEFAULT_CHUNKSIZE = 1_000_000

CATEGORY_COLUMNS = ["rent_station", "return_station", "bike_type"]


def normalize_station_name(name: str) -> str:
    """Make station names comparable across the rental file and station list.

    - removes the 'YouBike2.0_' prefix used in the real-time station list
    - strips surrounding whitespace
    - converts full-width parentheses to half-width

    The '_1' style suffix is kept on purpose: it may mark a different station
    at the same location, so it should be checked against the station list.
    """
    if pd.isna(name):
        return name
    name = str(name).strip()
    if name.startswith(STATION_PREFIX):
        name = name[len(STATION_PREFIX):]
    return name.replace("（", "(").replace("）", ")")


def prepare_stations(raw: pd.DataFrame) -> pd.DataFrame:
    """Turn the real-time station JSON into a tidy station table.

    The JSON has used both `lat`/`lng` and `latitude`/`longitude` over time,
    so both are accepted. Output columns: name, district, lat, lng, docks.
    """
    lat_col = "latitude" if "latitude" in raw.columns else "lat"
    lng_col = "longitude" if "longitude" in raw.columns else "lng"
    out = pd.DataFrame(
        {
            "name": raw["sna"].map(normalize_station_name),
            "district": raw.get("sarea"),
            "lat": pd.to_numeric(raw[lat_col], errors="coerce"),
            "lng": pd.to_numeric(raw[lng_col], errors="coerce"),
            "docks": pd.to_numeric(raw.get("total"), errors="coerce"),
        }
    )
    return out.drop_duplicates("name").reset_index(drop=True)


def month_from_path(path) -> str | None:
    """'data/raw/rawdata_202603.csv' -> '2026-03' (None if no YYYYMM found)."""
    m = re.search(r"(20\d{2})(0[1-9]|1[0-2])", Path(path).stem)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def clean_chunk(
    raw: pd.DataFrame,
    max_duration_min: float = DEFAULT_MAX_DURATION_MIN,
    min_same_station_min: float = DEFAULT_MIN_SAME_STATION_MIN,
) -> tuple[pd.DataFrame, dict]:
    """Clean one chunk of raw rows.

    Returns the cleaned rows and a dict with how many rows each rule removed.

    Output columns
    --------------
    date : datetime64, the rental date
    rent_hour, return_hour : int8, hour of day (0-23)
    rent_station, return_station : category, normalized station names
    duration_min : float32, ride duration in minutes
    bike_type : category, 'ebike' or 'regular'
    same_station : bool
    """
    rent_time = pd.to_datetime(raw["rent_time"], errors="coerce")
    return_time = pd.to_datetime(raw["return_time"], errors="coerce")
    rent_station = raw["rent_station"].map(normalize_station_name)
    return_station = raw["return_station"].map(normalize_station_name)
    duration = pd.to_timedelta(raw["rent"], errors="coerce").dt.total_seconds() / 60
    bike_type = raw["bike_type"].str.strip().map(BIKE_TYPE_MAP)
    date = pd.to_datetime(raw["infodate"], errors="coerce")

    missing = (
        rent_time.isna() | return_time.isna() | rent_station.isna()
        | return_station.isna() | duration.isna() | bike_type.isna() | date.isna()
    )
    same = rent_station == return_station
    too_long = ~missing & (duration > max_duration_min)
    failed = ~missing & ~too_long & (same & (duration < min_same_station_min) | (duration <= 0))
    keep = ~(missing | too_long | failed)

    out = pd.DataFrame(
        {
            "date": date[keep],
            "rent_hour": rent_time[keep].dt.hour.astype("int8"),
            "return_hour": return_time[keep].dt.hour.astype("int8"),
            "rent_station": rent_station[keep].astype("category"),
            "return_station": return_station[keep].astype("category"),
            "duration_min": duration[keep].astype("float32"),
            "bike_type": bike_type[keep].astype("category"),
            "same_station": same[keep],
        }
    )
    stats = {
        "n_raw": len(raw),
        "dropped_missing": int(missing.sum()),
        "dropped_too_long": int(too_long.sum()),
        "dropped_failed_rental": int(failed.sum()),
        "n_kept": int(keep.sum()),
    }
    return out, stats


def has_header(path) -> bool:
    """True if the first line is the column header.

    The files for 2025-08 to 2026-02 have no header row; later files do.
    Headerless files are assumed to use the same column order as RAW_COLUMNS.
    """
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        return f.readline().startswith("rent_time")


def iter_rental_chunks(path, chunksize: int = DEFAULT_CHUNKSIZE, **clean_kwargs):
    """Yield (cleaned_chunk, stats) for one raw CSV, reading it piece by piece."""
    if has_header(path):
        header_kwargs = {"usecols": RAW_COLUMNS}
    else:
        header_kwargs = {"header": None, "names": RAW_COLUMNS}
    reader = pd.read_csv(path, dtype=str, chunksize=chunksize,
                         encoding="utf-8-sig", **header_kwargs)
    for chunk in reader:
        yield clean_chunk(chunk, **clean_kwargs)


def concat_with_categories(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Concatenate frames while keeping category columns as categories
    (plain pd.concat turns mismatched categories into memory-hungry objects)."""
    frames = [f for f in frames if len(f)]
    if not frames:
        return pd.DataFrame()
    out = {}
    for col in frames[0].columns:
        if isinstance(frames[0][col].dtype, pd.CategoricalDtype):
            out[col] = pd.Series(union_categoricals([f[col] for f in frames]))
        else:
            out[col] = pd.concat([f[col] for f in frames], ignore_index=True)
    return pd.DataFrame(out)


def load_rentals(
    paths,
    sample_frac: float | None = None,
    bike_type: str | None = None,
    seed: int = 42,
    chunksize: int = DEFAULT_CHUNKSIZE,
    **clean_kwargs,
) -> pd.DataFrame:
    """Read one or more raw rental CSVs and return cleaned rows.

    For a whole month or more, prefer `build_interim()` + `load_interim()`:
    they clean each month once and then load in seconds.

    Parameters
    ----------
    paths : path or list of paths to raw CSV files
    sample_frac : keep only this fraction of rows (sampled per chunk,
        reproducible with `seed`). Useful to explore several months in memory.
    bike_type : 'ebike' or 'regular' to keep only one type
    clean_kwargs : passed to `clean_chunk` (max_duration_min, min_same_station_min)

    The returned DataFrame has `attrs["cleaning_report"]`: a list with one
    dict per file giving how many rows were read, kept and dropped by each
    rule. Use `pd.DataFrame(df.attrs["cleaning_report"])` to view it.
    """
    if isinstance(paths, (str, Path)):
        paths = [paths]

    frames, reports = [], []
    for path in paths:
        totals = {}
        for i, (chunk, stats) in enumerate(iter_rental_chunks(path, chunksize, **clean_kwargs)):
            for k, v in stats.items():
                totals[k] = totals.get(k, 0) + v
            if bike_type is not None:
                chunk = chunk[chunk["bike_type"] == bike_type]
            if sample_frac is not None:
                chunk = chunk.sample(frac=sample_frac, random_state=seed + i)
            frames.append(chunk)
        reports.append({"file": Path(path).name, "month": month_from_path(path), **totals})

    out = concat_with_categories(frames)
    out.attrs["cleaning_report"] = reports
    return out


def build_interim(
    raw_dir="data/raw",
    interim_dir="data/interim",
    overwrite: bool = False,
    pattern: str = "rawdata_*.csv",
    **clean_kwargs,
) -> pd.DataFrame:
    """Clean every raw month once and save it as `interim/trips_YYYYMM.parquet`.

    Months that already have a parquet file are skipped unless `overwrite`.
    Also writes `interim/cleaning_report.csv`. Returns that report.
    """
    raw_dir, interim_dir = Path(raw_dir), Path(interim_dir)
    interim_dir.mkdir(parents=True, exist_ok=True)
    report_path = interim_dir / "cleaning_report.csv"
    old = pd.read_csv(report_path) if report_path.exists() else pd.DataFrame()

    rows = []
    for path in sorted(raw_dir.glob(pattern)):
        month = month_from_path(path)
        target = interim_dir / f"trips_{month.replace('-', '')}.parquet"
        if target.exists() and not overwrite:
            print(f"skip {month} (already cleaned)")
            continue
        df = load_rentals(path, **clean_kwargs)
        rows.extend(df.attrs.pop("cleaning_report"))
        df.to_parquet(target, index=False)
        print(f"saved {target.name}: {len(df):,} rides")

    report = pd.concat([old, pd.DataFrame(rows)], ignore_index=True)
    if not report.empty:
        report = report.drop_duplicates("month", keep="last").sort_values("month")
        report.to_csv(report_path, index=False)
    return report


def load_interim(
    interim_dir="data/interim",
    months: list[str] | None = None,
    columns: list[str] | None = None,
    bike_type: str | None = None,
    sample_frac: float | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """Load cleaned months saved by `build_interim`.

    months : e.g. ['2026-03', '2026-04']; default all available
    columns : only read these columns (saves memory)
    bike_type : 'ebike' or 'regular'
    sample_frac : random fraction per month (reproducible with `seed`)
    """
    paths = sorted(Path(interim_dir).glob("trips_*.parquet"))
    if months is not None:
        wanted = {m.replace("-", "") for m in months}
        paths = [p for p in paths if p.stem.split("_")[1] in wanted]
    if not paths:
        raise FileNotFoundError(f"No cleaned months in {interim_dir}. Run build_interim() first.")

    read_cols = None
    if columns is not None:
        read_cols = list(dict.fromkeys(columns + (["bike_type"] if bike_type else [])))

    frames = []
    for i, p in enumerate(paths):
        df = pd.read_parquet(p, columns=read_cols)
        if bike_type is not None:
            df = df[df["bike_type"] == bike_type]
        if sample_frac is not None:
            df = df.sample(frac=sample_frac, random_state=seed + i)
        if columns is not None:
            df = df[columns]
        frames.append(df)
    return concat_with_categories(frames)
