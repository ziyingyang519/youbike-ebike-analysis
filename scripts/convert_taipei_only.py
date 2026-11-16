"""Convert the team's Taipei-only trip archives into monthly parquet files.

Input : data/raw/taipei_only_zips/trips_YYYYMM_taipei_only_coordinates_csv_NN.zip
        (made by a teammate from data/interim/trips_YYYYMM.parquet; both trip
        endpoints uniquely matched to a Taipei City station, plus coordinates)
Output: data/interim/trips_YYYYMM.parquet  (same columns as before + 4 coordinate columns)
        data/interim/taipei_only_check.csv (row counts vs MANIFEST.json, SHA-256 check)

Usage : python scripts/convert_taipei_only.py [YYYYMM ...]
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
ZIP_DIR = ROOT / "data" / "raw" / "taipei_only_zips"
OUT_DIR = ROOT / "data" / "interim"

DTYPES = {
    "rent_hour": "int8", "return_hour": "int8", "duration_min": "float32",
    "bike_type": "category", "same_station": "bool",
    "rent_latitude": "float32", "rent_longitude": "float32",
    "return_latitude": "float32", "return_longitude": "float32",
}


def convert_month(month: str) -> dict:
    zips = sorted(ZIP_DIR.glob(f"trips_{month}_taipei_only_coordinates_csv_*.zip"))
    if not zips:
        raise FileNotFoundError(f"no archives for {month} in {ZIP_DIR}")
    frames, expected, bad_sha = [], None, 0
    for z in zips:
        with zipfile.ZipFile(z) as zf:
            manifest = json.loads(zf.read("MANIFEST.json"))
            expected = manifest["retained_rows_in_month"]
            for part in manifest["parts"]:
                data = zf.read(part["file_name"])
                if hashlib.sha256(data).hexdigest() != part["sha256"]:
                    bad_sha += 1
                df = pd.read_csv(io.BytesIO(data), encoding="utf-8-sig", dtype=DTYPES)
                assert len(df) == part["rows"], part["file_name"]
                df["date"] = pd.to_datetime(df["date"]).astype("datetime64[ms]")
                for c in ("rent_station", "return_station"):
                    df[c] = df[c].astype("category")
                frames.append((part["file_name"], df))
    frames.sort(key=lambda t: t[0])  # keep part order
    dfs = [f for _, f in frames]
    # unify categories so the month is one table
    for c in ("rent_station", "return_station", "bike_type"):
        cats = pd.api.types.union_categoricals([d[c] for d in dfs]).categories
        for d in dfs:
            d[c] = d[c].cat.set_categories(cats)
    month_df = pd.concat(dfs, ignore_index=True)
    del dfs, frames
    out = OUT_DIR / f"trips_{month}.parquet"
    month_df.to_parquet(out, index=False)
    return {
        "month": f"{month[:4]}-{month[4:]}", "archives": len(zips),
        "rows": len(month_df), "manifest_rows": expected,
        "rows_match": len(month_df) == expected, "sha256_failures": bad_sha,
        "rent_stations": month_df["rent_station"].nunique(),
        "ebike_share": round((month_df["bike_type"] == "ebike").mean(), 4),
    }


def main(months: list[str]) -> None:
    if not months:
        months = sorted({p.name.split("_")[1] for p in ZIP_DIR.glob("trips_*.zip")})
    check_path = OUT_DIR / "taipei_only_check.csv"
    old = pd.read_csv(check_path) if check_path.exists() else pd.DataFrame()
    rows = []
    for m in months:
        r = convert_month(m)
        print(r, flush=True)
        rows.append(r)
    new = pd.DataFrame(rows)
    if not old.empty:
        old = old[~old["month"].isin(new["month"])]
    pd.concat([old, new]).sort_values("month").to_csv(check_path, index=False)


if __name__ == "__main__":
    main(sys.argv[1:])
