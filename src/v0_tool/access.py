"""Geometric ground-access analysis using Skyfield.

This module calculates line-of-sight geometric access windows between an SGP4
satellite and a fixed ground station above a minimum-elevation threshold.

Offline time handling:
    skyfield.api.load.timescale(builtin=True) is used to load immutable built-in
    timescale tables without performing network calls or reading external delta-t files.
    This guarantees deterministic and offline behavior for the fixed installed
    Skyfield version.

Coordinate frame separation:
    Orbital propagation uses analytical SGP4 in TEME governed by the selected
    gravity constants (WGS72). Ground-station topocentric coordinates are defined
    on Skyfield's WGS84 terrestrial ellipsoid (skyfield.api.wgs84).
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from skyfield.api import EarthSatellite, load, wgs84

from v0_tool.config import GroundStationConfig
from v0_tool.sgp4_adapter import Sgp4SatelliteRecord

# Skyfield event codes returned by EarthSatellite.find_events()
EVENT_RISE = 0
EVENT_CULMINATE = 1
EVENT_SET = 2

# Small numerical tolerance for evaluating initial visibility against minimum elevation
ELEVATION_TOLERANCE_DEG = 1e-9


class AccessEventSequenceError(ValueError):
    """Raised when an event sequence violates physical or logical pass structure."""

    pass


@dataclass(frozen=True)
class AccessWindow:
    """Library-independent record of an unbroken geometric ground-access opportunity.

    Represents a continuous time interval during which the line-of-sight elevation
    from a fixed ground station to a satellite meets or exceeds the configured threshold.
    """

    satellite_id: str
    ground_station_id: str
    start_time_utc: datetime
    end_time_utc: datetime
    duration_seconds: float
    minimum_elevation_deg: float
    culmination_time_utc: datetime | None = None
    maximum_elevation_deg: float | None = None
    access_type: str = "geometric_elevation"
    geometry_method: str = "skyfield_find_events"


def parse_access_events(
    satellite_id: str,
    ground_station_id: str,
    minimum_elevation_deg: float,
    start_time_utc: datetime,
    end_time_utc: datetime,
    initial_elevation_deg: float,
    event_times_utc: list[datetime],
    event_codes: list[int],
    event_elevations_deg: list[float | None] | None = None,
) -> tuple[AccessWindow, ...]:
    """Parse raw (time, event_code) events into discrete, validated AccessWindow records.

    Handles boundary clippings (visible at t0, visible at t1, visible throughout)
    and multiple culminations per pass.

    Args:
        satellite_id: String satellite identifier.
        ground_station_id: String ground station identifier.
        minimum_elevation_deg: Minimum elevation threshold in degrees.
        start_time_utc: Inclusive analysis start in UTC.
        end_time_utc: Inclusive analysis end in UTC.
        initial_elevation_deg: Topocentric elevation at start_time_utc in degrees.
        event_times_utc: List of timezone-aware UTC event datetimes.
        event_codes: List of Skyfield event integer codes (0=rise, 1=culminate, 2=set).
        event_elevations_deg: Optional list of elevations matching event_codes.
            Culmination events must have a valid float elevation.

    Returns:
        tuple[AccessWindow, ...]: Chronologically ordered access windows.

    Raises:
        AccessEventSequenceError: If event lengths mismatch, culmination lacks elevation,
            or the transition sequence is logically impossible.
    """
    n_events = len(event_times_utc)
    if len(event_codes) != n_events:
        raise AccessEventSequenceError(
            f"Event count mismatch: {len(event_codes)} codes vs {n_events} times "
            f"for {satellite_id} -> {ground_station_id}."
        )

    if event_elevations_deg is not None:
        if len(event_elevations_deg) != n_events:
            raise AccessEventSequenceError(
                f"Elevations count mismatch: {len(event_elevations_deg)} elevations vs "
                f"{n_events} events for {satellite_id} -> {ground_station_id}."
            )
        elevations = event_elevations_deg
    else:
        elevations = [None] * n_events

    # Determine initial visibility at start_time_utc with tolerance
    in_view = initial_elevation_deg >= (minimum_elevation_deg - ELEVATION_TOLERANCE_DEG)

    active_start: datetime | None = start_time_utc if in_view else None
    best_culm_time: datetime | None = None
    best_culm_elev: float | None = None

    windows: list[AccessWindow] = []

    for i in range(n_events):
        t_event = event_times_utc[i]
        code = event_codes[i]
        elev = elevations[i]

        if not (start_time_utc <= t_event <= end_time_utc):
            raise AccessEventSequenceError(
                f"Event at {t_event} lies outside analysis bounds "
                f"[{start_time_utc}, {end_time_utc}] for {satellite_id} -> {ground_station_id}."
            )

        if code == EVENT_RISE:
            if in_view:
                raise AccessEventSequenceError(
                    f"Unexpected rise event at {t_event}: satellite is already in view "
                    f"for {satellite_id} -> {ground_station_id}."
                )
            in_view = True
            active_start = t_event
            best_culm_time = None
            best_culm_elev = None

        elif code == EVENT_CULMINATE:
            if not in_view:
                raise AccessEventSequenceError(
                    f"Unexpected culmination event at {t_event} while out of view "
                    f"for {satellite_id} -> {ground_station_id}."
                )
            if elev is None:
                raise AccessEventSequenceError(
                    f"Culmination event at index {i} ({t_event}) lacks evaluated elevation "
                    f"for {satellite_id} -> {ground_station_id}."
                )
            # If multiple culminations occur, retain the one with higher elevation
            if best_culm_elev is None or elev > best_culm_elev:
                best_culm_elev = elev
                best_culm_time = t_event

        elif code == EVENT_SET:
            if not in_view or active_start is None:
                raise AccessEventSequenceError(
                    f"Unexpected set event at {t_event} while out of view "
                    f"for {satellite_id} -> {ground_station_id}."
                )

            duration = (t_event - active_start).total_seconds()
            if duration <= 0:
                raise AccessEventSequenceError(
                    f"Non-positive window duration ({duration} s) ending at {t_event} "
                    f"for {satellite_id} -> {ground_station_id}."
                )

            windows.append(
                AccessWindow(
                    satellite_id=satellite_id,
                    ground_station_id=ground_station_id,
                    start_time_utc=active_start,
                    end_time_utc=t_event,
                    duration_seconds=duration,
                    minimum_elevation_deg=minimum_elevation_deg,
                    culmination_time_utc=best_culm_time,
                    maximum_elevation_deg=best_culm_elev,
                )
            )
            in_view = False
            active_start = None
            best_culm_time = None
            best_culm_elev = None

        else:
            raise AccessEventSequenceError(
                f"Unknown Skyfield event code {code} at {t_event} "
                f"for {satellite_id} -> {ground_station_id}."
            )

    # Legitimate boundary clipping: satellite remains visible at analysis end
    if in_view and active_start is not None:
        duration = (end_time_utc - active_start).total_seconds()
        if duration > 0:
            windows.append(
                AccessWindow(
                    satellite_id=satellite_id,
                    ground_station_id=ground_station_id,
                    start_time_utc=active_start,
                    end_time_utc=end_time_utc,
                    duration_seconds=duration,
                    minimum_elevation_deg=minimum_elevation_deg,
                    culmination_time_utc=best_culm_time,
                    maximum_elevation_deg=best_culm_elev,
                )
            )

    return tuple(windows)


def calculate_access_windows(
    satellite_record: Sgp4SatelliteRecord,
    ground_station: GroundStationConfig,
    start_time_utc: datetime,
    end_time_utc: datetime,
) -> tuple[AccessWindow, ...]:
    """Calculate geometric access windows between a satellite and a ground station.

    Reuses the existing SGP4 Satrec record inside EarthSatellite.from_satrec.
    Uses skyfield.api.load.timescale(builtin=True) for offline execution.

    Args:
        satellite_record: Sgp4SatelliteRecord with initialized Satrec.
        ground_station: Validated GroundStationConfig.
        start_time_utc: Inclusive analysis start in UTC.
        end_time_utc: Inclusive analysis end in UTC.

    Returns:
        tuple[AccessWindow, ...]: Chronologically ordered access windows.

    Raises:
        ValueError: If analysis timestamps are invalid.
        AccessEventSequenceError: If event parsing detects an inconsistent sequence.
    """
    if start_time_utc.tzinfo is None or end_time_utc.tzinfo is None:
        raise ValueError("start_time_utc and end_time_utc must be timezone-aware.")
    if start_time_utc.utcoffset() != timedelta(0) or end_time_utc.utcoffset() != timedelta(0):
        raise ValueError("start_time_utc and end_time_utc must have UTC offset (+00:00 or Z).")
    if end_time_utc <= start_time_utc:
        raise ValueError(
            f"end_time_utc ({end_time_utc}) must be strictly after start_time_utc ({start_time_utc})."
        )

    # 1. Initialize offline timescale and Skyfield objects
    ts = load.timescale(builtin=True)
    earth_sat = EarthSatellite.from_satrec(satellite_record.satrec, ts)

    topos_station = wgs84.latlon(
        latitude_degrees=ground_station.latitude_deg,
        longitude_degrees=ground_station.longitude_deg,
        elevation_m=ground_station.altitude_m,
    )

    t0 = ts.from_datetime(start_time_utc)
    t1 = ts.from_datetime(end_time_utc)

    # 2. Check initial elevation at t0 to establish initial visibility
    diff = earth_sat - topos_station
    alt0, _, _ = diff.at(t0).altaz()
    initial_elev_deg = float(alt0.degrees)

    # 3. Find raw geometric events using Skyfield root-finding
    raw_times, raw_codes = earth_sat.find_events(
        topos_station,
        t0,
        t1,
        altitude_degrees=ground_station.minimum_elevation_deg,
    )

    # 4. Convert Skyfield Time objects to UTC datetimes and evaluate culmination elevations
    event_times_utc: list[datetime] = []
    event_codes_list: list[int] = []
    event_elevations: list[float | None] = []

    for t_sk, code in zip(raw_times, raw_codes):
        dt_utc = t_sk.utc_datetime()
        event_times_utc.append(dt_utc)
        event_codes_list.append(int(code))

        if int(code) == EVENT_CULMINATE:
            alt_culm, _, _ = diff.at(t_sk).altaz()
            event_elevations.append(float(alt_culm.degrees))
        else:
            event_elevations.append(None)

    # 5. Parse events into discrete AccessWindow records via state machine
    return parse_access_events(
        satellite_id=satellite_record.satellite_id,
        ground_station_id=ground_station.station_id,
        minimum_elevation_deg=ground_station.minimum_elevation_deg,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
        initial_elevation_deg=initial_elev_deg,
        event_times_utc=event_times_utc,
        event_codes=event_codes_list,
        event_elevations_deg=event_elevations,
    )
