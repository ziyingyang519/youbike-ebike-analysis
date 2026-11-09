from pathlib import Path

import pandas as pd
import pytest

from youbike import (
    apply_name_fixes,
    find_question_mark_fixes,
    add_trip_features,
    build_interim,
    day_type,
    haversine_km,
    load_interim,
    load_rentals,
    normalize_station_name,
    prepare_stations,
    station_hour_counts,
    station_match_report,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_rentals.csv"


def test_normalize_station_name():
    assert normalize_station_name("YouBike2.0_捷運大安站(4號出口)") == "捷運大安站(4號出口)"
    assert normalize_station_name(" 捷運大安站（4號出口） ") == "捷運大安站(4號出口)"
    # '_1' suffix is kept on purpose
    assert normalize_station_name("捷運芝山站(2號出口)_1") == "捷運芝山站(2號出口)_1"


def test_load_rentals_cleaning_rules():
    df = load_rentals(FIXTURE, chunksize=3)  # small chunks to test chunked reading
    report = df.attrs["cleaning_report"][0]
    assert report["n_raw"] == 10
    assert report["dropped_missing"] == 1        # empty station name
    assert report["dropped_too_long"] == 1       # 310-minute ride
    assert report["dropped_failed_rental"] == 2  # 0 s and 40 s same-station returns
    assert report["n_kept"] == len(df) == 6
    # a 50-second ride to another station is kept
    assert (df["duration_min"] < 1).sum() == 1

    assert set(df["bike_type"].astype(str)) == {"ebike", "regular"}
    assert df["rent_station"].dtype == "category"
    first = df.iloc[0]
    assert first["duration_min"] == pytest.approx(22 + 35 / 60, abs=1e-4)
    assert first["rent_hour"] == 6 and first["return_hour"] == 7


def test_headerless_file(tmp_path):
    lines = FIXTURE.read_text(encoding="utf-8").splitlines(keepends=True)
    no_header = tmp_path / "rawdata_202508.csv"
    no_header.write_text("".join(lines[1:]), encoding="utf-8")
    pd.testing.assert_frame_equal(load_rentals(no_header), load_rentals(FIXTURE))


def test_load_rentals_filters():
    assert set(load_rentals(FIXTURE, bike_type="ebike")["bike_type"].astype(str)) == {"ebike"}
    a = load_rentals(FIXTURE, sample_frac=0.5, seed=1)
    b = load_rentals(FIXTURE, sample_frac=0.5, seed=1)
    pd.testing.assert_frame_equal(a, b)  # sampling is reproducible


def test_build_and_load_interim(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "rawdata_202607.csv").write_bytes(FIXTURE.read_bytes())
    interim = tmp_path / "interim"

    report = build_interim(raw, interim)
    assert (interim / "trips_202607.parquet").exists()
    assert report.loc[0, "month"] == "2026-07"
    # second run skips the month
    build_interim(raw, interim)

    df = load_interim(interim, months=["2026-07"], columns=["rent_station", "duration_min"])
    assert list(df.columns) == ["rent_station", "duration_min"] and len(df) == 6
    assert set(load_interim(interim, bike_type="ebike")["bike_type"].astype(str)) == {"ebike"}

    counts = station_hour_counts(interim)
    assert counts["n"].sum() == 6
    assert set(counts.columns) == {"rent_station", "day_type", "rent_hour", "bike_type", "n"}


def test_day_type():
    out = day_type(["2026-07-17", "2026-07-18", "2026-10-10"],
                   holidays={pd.Timestamp("2026-10-10").date()})
    assert list(out) == ["weekday", "holiday", "holiday"]


def test_haversine_known_distance():
    # Taipei Main Station to Taipei 101 is about 5 km in a straight line
    d = haversine_km(25.0478, 121.5170, 25.0340, 121.5645)
    assert 4.5 < d < 5.5


def test_add_trip_features():
    trips = load_rentals(FIXTURE)
    raw_stations = pd.DataFrame(
        {
            "sna": ["YouBike2.0_龍門廣場", "YouBike2.0_臺北遠企購物中心"],
            "sarea": ["大安區", "大安區"],
            "latitude": [25.0410, 25.0335],
            "longitude": [121.5440, 121.5500],
            "total": [40, 30],
        }
    )
    stations = prepare_stations(raw_stations)
    out = add_trip_features(trips, stations)

    first = out.iloc[0]
    assert first["day_type"] == "weekday"  # 2026-07-17 is a Friday
    assert first["distance_km"] > 0
    assert first["speed_kmh"] == pytest.approx(
        first["distance_km"] / (first["duration_min"] / 60), rel=1e-4)

    missing = station_match_report(trips, stations)
    assert "捷運芝山站(2號出口)_1" in set(missing["station"])


def test_question_mark_fixes():
    stations = ["瑠公公園", "福林國小", "士林國小", "公舘承德路口"]
    trips_names = ["?公公園", "?林國小", "公?承德路口", "龍門廣場"]
    fixes = find_question_mark_fixes(trips_names, stations)
    # '?林國小' matches two stations, so it is not fixed
    assert dict(zip(fixes.raw_name, fixes.fixed_name)) == {
        "?公公園": "瑠公公園", "公?承德路口": "公舘承德路口"}

    trips = pd.DataFrame({
        "rent_station": pd.Categorical(["?公公園", "瑠公公園", "龍門廣場"]),
        "return_station": ["公?承德路口", "龍門廣場", "?林國小"],
    })
    out = apply_name_fixes(trips, fixes)
    assert list(out["rent_station"]) == ["瑠公公園", "瑠公公園", "龍門廣場"]
    assert list(out["return_station"]) == ["公舘承德路口", "龍門廣場", "?林國小"]
