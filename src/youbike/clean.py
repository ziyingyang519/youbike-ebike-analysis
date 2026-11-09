"""Load and clean YouBike 2.0 rental records.

Raw columns (confirmed from the 2026-07 file):
    rent_time, rent_station, return_time, return_station, rent, bike_type, infodate

Notes
-----
- rent_time / return_time are truncated to the hour (e.g. 17:00:00).
- `rent` is the ride duration as HH:MM:SS, precise to the second.
- bike_type is '電輔車' (e-bike) or '一般車' (regular bike).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

BIKE_TYPE_MAP = {"電輔車": "ebike", "一般車": "regular"}
STATION_PREFIX = "YouBike2.0_"


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


def _read_one(path: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "big5", "cp950"):
        try:
            return pd.read_csv(path, encoding=enc, dtype=str)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Cannot decode {path}")


def load_rentals(paths) -> pd.DataFrame:
    """Read one or more raw rental CSV files and return a cleaned DataFrame.

    Output columns
    --------------
    rent_hour, return_hour : datetime (hour resolution)
    rent_station, return_station : normalized station names
    duration_min : float, ride duration in minutes
    bike_type : 'ebike' or 'regular'
    date : datetime.date
    """
    if isinstance(paths, (str, Path)):
        paths = [paths]
    df = pd.concat([_read_one(Path(p)) for p in paths], ignore_index=True)

    out = pd.DataFrame(
        {
            "rent_hour": pd.to_datetime(df["rent_time"], errors="coerce"),
            "return_hour": pd.to_datetime(df["return_time"], errors="coerce"),
            "rent_station": df["rent_station"].map(normalize_station_name),
            "return_station": df["return_station"].map(normalize_station_name),
            "duration_min": pd.to_timedelta(df["rent"], errors="coerce").dt.total_seconds() / 60,
            "bike_type": df["bike_type"].str.strip().map(BIKE_TYPE_MAP),
            "date": pd.to_datetime(df["infodate"], errors="coerce").dt.date,
        }
    )

    n_before = len(out)
    out = out.dropna(subset=["rent_hour", "rent_station", "return_station", "duration_min", "bike_type"])
    # Remove zero-length rides (likely docking errors)
    out = out[out["duration_min"] > 0]
    out.attrs["n_dropped"] = n_before - len(out)
    return out.reset_index(drop=True)
