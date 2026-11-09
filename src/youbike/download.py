"""Download Taipei YouBike 2.0 open data.

Sources
-------
- Rental records (monthly ZIP files), Taipei City Department of Transportation:
  https://data.taipei/dataset/detail?id=c5924c17-25db-4f1e-99c4-f8ada40f2445
- Real-time station information (station names, coordinates, docks).
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd
import requests

# Index CSV that lists the URL of every monthly file.
RENTAL_INDEX_URL = (
    "https://data.taipei/api/frontstage/tpeod/dataset/resource.download"
    "?rid=1105750a-e8f5-4b89-9f7f-006493bb6de7"
)
STATION_INFO_URL = (
    "https://tcgbusfs.blob.core.windows.net/dotapp/youbike/v2/youbike_immediate.json"
)


def _read_csv_any_encoding(source, **kwargs) -> pd.DataFrame:
    """Read a CSV that may be UTF-8 (with or without BOM) or Big5."""
    last_error = None
    for enc in ("utf-8-sig", "big5", "cp950"):
        try:
            if hasattr(source, "seek"):
                source.seek(0)
            return pd.read_csv(source, encoding=enc, **kwargs)
        except UnicodeDecodeError as err:
            last_error = err
    raise last_error


def get_rental_index() -> pd.DataFrame:
    """Return the list of monthly files with a `month` column like '2026-03'."""
    resp = requests.get(RENTAL_INDEX_URL, timeout=60)
    resp.raise_for_status()
    idx = _read_csv_any_encoding(io.BytesIO(resp.content))
    # fileinfo looks like '2026/3/1'
    idx["month"] = pd.to_datetime(idx["fileinfo"], format="%Y/%m/%d").dt.strftime("%Y-%m")
    return idx.sort_values("month").reset_index(drop=True)


def download_month(month: str, raw_dir: str | Path = "data/raw") -> list[Path]:
    """Download and unzip one month of rental records.

    Parameters
    ----------
    month : str
        Month in 'YYYY-MM' format, e.g. '2026-03'.
    raw_dir : path
        Folder to extract the CSV files into.

    Returns
    -------
    List of extracted CSV paths.
    """
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    idx = get_rental_index()
    match = idx.loc[idx["month"] == month, "fileURL"]
    if match.empty:
        available = ", ".join(idx["month"].tolist())
        raise ValueError(f"Month {month} not found. Available: {available}")

    resp = requests.get(match.iloc[0], timeout=600)
    resp.raise_for_status()

    out_paths = []
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        for name in zf.namelist():
            if not name.lower().endswith(".csv"):
                continue
            target = raw_dir / f"{month}_{Path(name).name}"
            target.write_bytes(zf.read(name))
            out_paths.append(target)
    return out_paths


def download_station_info(out_path: str | Path = "data/external/stations.csv") -> pd.DataFrame:
    """Download the current station list (name, district, lat, lng, docks)."""
    resp = requests.get(STATION_INFO_URL, timeout=60)
    resp.raise_for_status()
    stations = pd.DataFrame(resp.json())
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    stations.to_csv(out_path, index=False, encoding="utf-8-sig")
    return stations
