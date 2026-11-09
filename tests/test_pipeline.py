from pathlib import Path

import pandas as pd
import pytest

from youbike import (
    add_trip_features,
    haversine_km,
    load_rentals,
    normalize_station_name,
    prepare_stations,
    station_match_report,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_rentals.csv"


def test_normalize_station_name():
    assert normalize_station_name("YouBike2.0_捷運大安站(4號出口)") == "捷運大安站(4號出口)"
    assert normalize_station_name(" 捷運大安站（4號出口） ") == "捷運大安站(4號出口)"
    # '_1' suffix is kept on purpose
    assert normalize_station_name("捷運芝山站(2號出口)_1") == "捷運芝山站(2號出口)_1"


def test_load_rentals():
    df = load_rentals(FIXTURE)
    # the zero-duration ride is removed
    assert len(df) == 5
    assert df.attrs["n_dropped"] == 1
    assert set(df["bike_type"]) == {"ebike", "regular"}
    assert df.loc[0, "duration_min"] == pytest.approx(22 + 35 / 60)
    assert df.loc[0, "rent_hour"] == pd.Timestamp("2026-07-17 06:00:00")


def test_haversine_known_distance():
    # Taipei Main Station to Taipei 101 is about 5.4 km in a straight line
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
    assert first["hour"] == 6
    assert first["day_type"] == "weekday"  # 2026-07-17 is a Friday
    assert first["distance_km"] > 0
    assert first["speed_kmh"] == pytest.approx(first["distance_km"] / (first["duration_min"] / 60))

    missing = station_match_report(trips, stations)
    assert "捷運芝山站(2號出口)_1" in set(missing["station"])
