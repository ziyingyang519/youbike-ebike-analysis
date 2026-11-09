"""Clean raw monthly CSVs once and save them as parquet in data/interim/.

Usage
-----
    python scripts/prepare_data.py                     # every month in data/raw
    python scripts/prepare_data.py --months 2026-03    # only some months
    python scripts/prepare_data.py --overwrite         # redo months already cleaned
    python scripts/prepare_data.py --max-duration 180  # change a cleaning rule

Each month takes roughly half a minute to a few minutes depending on the computer.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from youbike.clean import (  # noqa: E402
    DEFAULT_MAX_DURATION_MIN,
    DEFAULT_MIN_SAME_STATION_MIN,
    build_interim,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--months", nargs="+", help="Months in YYYY-MM format (default: all)")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--max-duration", type=float, default=DEFAULT_MAX_DURATION_MIN,
                        help=f"Drop rides longer than this many minutes (default {DEFAULT_MAX_DURATION_MIN})")
    parser.add_argument("--min-same-station", type=float, default=DEFAULT_MIN_SAME_STATION_MIN,
                        help=f"Drop same-station rides shorter than this (default {DEFAULT_MIN_SAME_STATION_MIN})")
    args = parser.parse_args()

    patterns = (
        [f"rawdata_{m.replace('-', '')}.csv" for m in args.months] if args.months else ["rawdata_*.csv"]
    )
    for pattern in patterns:
        report = build_interim(
            ROOT / "data" / "raw",
            ROOT / "data" / "interim",
            overwrite=args.overwrite,
            pattern=pattern,
            max_duration_min=args.max_duration,
            min_same_station_min=args.min_same_station,
        )
    print("\nCleaning report (data/interim/cleaning_report.csv):")
    print(report.to_string(index=False))


if __name__ == "__main__":
    main()
