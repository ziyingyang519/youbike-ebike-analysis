"""Trip-level features: distance, speed, time of day, day type."""

from __future__ import annotations

import numpy as np
import pandas as pd

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km. Works on scalars or arrays."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def add_trip_features(
    trips: pd.DataFrame,
    stations: pd.DataFrame,
    holidays: set | None = None,
) -> pd.DataFrame:
    """Add distance, speed and time features to cleaned trips.

    Parameters
    ----------
    trips : output of `load_rentals`
    stations : DataFrame with columns `name`, `lat`, `lng`
        (and optionally `elevation_m` once the DEM is joined)
    holidays : set of datetime.date that are days off (weekends are added
        automatically). Use the government office calendar so that
        make-up workdays and long weekends are handled correctly.
    """
    st = stations.set_index("name")
    out = trips.copy()

    for side in ("rent", "return"):
        coords = st.reindex(out[f"{side}_station"])
        out[f"{side}_lat"] = coords["lat"].to_numpy()
        out[f"{side}_lng"] = coords["lng"].to_numpy()
        if "elevation_m" in st.columns:
            out[f"{side}_elev"] = coords["elevation_m"].to_numpy()

    out["same_station"] = out["rent_station"] == out["return_station"]
    out["distance_km"] = haversine_km(
        out["rent_lat"], out["rent_lng"], out["return_lat"], out["return_lng"]
    )
    # Speed is only meaningful for A-to-B trips
    out["speed_kmh"] = np.where(
        out["same_station"], np.nan, out["distance_km"] / (out["duration_min"] / 60)
    )
    if "rent_elev" in out.columns:
        out["elev_gain_m"] = out["return_elev"] - out["rent_elev"]

    out["hour"] = out["rent_hour"].dt.hour
    dates = pd.to_datetime(out["date"])
    is_weekend = dates.dt.dayofweek >= 5
    if holidays:
        is_off = is_weekend | out["date"].isin(holidays)
    else:
        is_off = is_weekend
    out["day_type"] = np.where(is_off, "holiday", "weekday")
    return out


def station_match_report(trips: pd.DataFrame, stations: pd.DataFrame) -> pd.DataFrame:
    """List rental station names that are missing from the station list,
    with how many trips each one has, so they can be fixed by hand."""
    known = set(stations["name"])
    counts = pd.concat([trips["rent_station"], trips["return_station"]]).value_counts()
    missing = counts[~counts.index.isin(known)]
    return missing.rename("n_trips").rename_axis("station").reset_index()
