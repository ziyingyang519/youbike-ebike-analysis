"""Trip-level features and station-level aggregates."""

from __future__ import annotations

from pathlib import Path

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


def day_type(dates, holidays: set | None = None) -> pd.Series:
    """'weekday' or 'holiday' for each date.

    Weekends count as holidays. Pass `holidays` (a set of datetime.date from
    the government office calendar) to also mark national holidays; make-up
    workdays can be handled by passing `workdays` in a later version.
    """
    dates = pd.to_datetime(pd.Series(dates))
    off = dates.dt.dayofweek >= 5
    if holidays:
        off = off | dates.dt.date.isin(holidays)
    return pd.Series(np.where(off, "holiday", "weekday"), index=dates.index, dtype="category")


def add_trip_features(
    trips: pd.DataFrame,
    stations: pd.DataFrame,
    holidays: set | None = None,
) -> pd.DataFrame:
    """Add distance, speed and day type to cleaned trips.

    Parameters
    ----------
    trips : output of `load_rentals` / `load_interim`
    stations : DataFrame with columns `name`, `lat`, `lng`
        (and optionally `elevation_m` once the DEM is joined)
    holidays : set of datetime.date that are days off (see `day_type`)
    """
    st = stations.set_index("name")
    out = trips.copy()

    for side in ("rent", "return"):
        coords = st.reindex(out[f"{side}_station"].astype(str))
        out[f"{side}_lat"] = coords["lat"].to_numpy()
        out[f"{side}_lng"] = coords["lng"].to_numpy()
        if "elevation_m" in st.columns:
            out[f"{side}_elev"] = coords["elevation_m"].to_numpy()

    if "same_station" not in out.columns:
        out["same_station"] = out["rent_station"].astype(str) == out["return_station"].astype(str)

    out["distance_km"] = haversine_km(
        out["rent_lat"], out["rent_lng"], out["return_lat"], out["return_lng"]
    ).astype("float32")
    # Speed is only meaningful for A-to-B trips
    out["speed_kmh"] = np.where(
        out["same_station"], np.nan, out["distance_km"] / (out["duration_min"] / 60)
    ).astype("float32")
    if "rent_elev" in out.columns:
        out["elev_gain_m"] = out["return_elev"] - out["rent_elev"]

    out["day_type"] = day_type(out["date"], holidays).to_numpy()
    return out


def station_match_report(trips: pd.DataFrame, stations: pd.DataFrame) -> pd.DataFrame:
    """List rental station names that are missing from the station list,
    with how many trips each one has, so they can be fixed by hand."""
    known = set(stations["name"])
    counts = pd.concat(
        [trips["rent_station"].astype(str), trips["return_station"].astype(str)]
    ).value_counts()
    missing = counts[~counts.index.isin(known)]
    return missing.rename("n_trips").rename_axis("station").reset_index()


def station_hour_counts(
    interim_dir="data/interim",
    months: list[str] | None = None,
    holidays: set | None = None,
) -> pd.DataFrame:
    """Count rentals by station x day type x hour x bike type, month by month.

    This never loads more than one month at a time, so it works on the whole
    year. Returns a long table with columns
    rent_station, day_type, rent_hour, bike_type, n.
    """
    from .clean import load_interim  # local import to avoid a cycle

    paths = sorted(Path(interim_dir).glob("trips_*.parquet"))
    month_ids = [p.stem.split("_")[1] for p in paths]
    if months is not None:
        wanted = {m.replace("-", "") for m in months}
        month_ids = [m for m in month_ids if m in wanted]

    parts = []
    for m in month_ids:
        df = load_interim(interim_dir, months=[f"{m[:4]}-{m[4:]}"],
                          columns=["date", "rent_station", "rent_hour", "bike_type"])
        df["day_type"] = day_type(df["date"], holidays).to_numpy()
        df["rent_station"] = df["rent_station"].astype(str)
        parts.append(
            df.groupby(["rent_station", "day_type", "rent_hour", "bike_type"],
                       observed=True).size().rename("n")
        )
    total = pd.concat(parts).groupby(level=[0, 1, 2, 3], observed=True).sum()
    return total.reset_index()
