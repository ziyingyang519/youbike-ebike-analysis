"""Download rental records and the station list.

Usage
-----
    python scripts/download_data.py --month 2026-03
    python scripts/download_data.py --month 2026-01 2026-02 2026-03
    python scripts/download_data.py --list        # show available months
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from youbike.download import download_month, download_station_info, get_rental_index  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--month", nargs="+", help="Months in YYYY-MM format")
    parser.add_argument("--list", action="store_true", help="List available months and exit")
    parser.add_argument("--skip-stations", action="store_true", help="Do not download the station list")
    args = parser.parse_args()

    if args.list:
        print("\n".join(get_rental_index()["month"]))
        return

    if not args.month:
        parser.error("give --month or --list")

    for month in args.month:
        paths = download_month(month, ROOT / "data" / "raw")
        for p in paths:
            print(f"saved {p.relative_to(ROOT)}")

    if not args.skip_stations:
        stations = download_station_info(ROOT / "data" / "external" / "stations.csv")
        print(f"saved data/external/stations.csv ({len(stations)} stations)")


if __name__ == "__main__":
    main()
