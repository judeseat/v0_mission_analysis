"""Unit, state-machine, and integration tests for geometric access analysis (Stage 1 Task 5).

Note on testing scope:
    Tests verify the Skyfield adapter, parsing state machine, boundary conditions,
    and threshold monotonicity. They do not assert hardcoded external pass times
    as independent validation.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
from skyfield.api import EarthSatellite, load, wgs84

from v0_tool.access import (
    AccessEventSequenceError,
    AccessWindow,
    calculate_access_windows,
    parse_access_events,
)
from v0_tool.config import GroundStationConfig, SatelliteConfig, load_scenario
from v0_tool.sgp4_adapter import create_sgp4_satellite


def _sample_satellite_config() -> SatelliteConfig:
    return SatelliteConfig(
        satellite_id="SAT-SMOKE-01",
        altitude_km=550.0,
        inclination_deg=53.0,
        eccentricity=0.0,
        raan_deg=0.0,
        arg_perigee_deg=0.0,
        mean_anomaly_deg=0.0,
        bstar=0.0,
    )


def _sample_station_config(min_elev: float = 10.0) -> GroundStationConfig:
    return GroundStationConfig(
        station_id="GS-SMOKE-01",
        latitude_deg=0.0,
        longitude_deg=-60.0,
        altitude_m=0.0,
        minimum_elevation_deg=min_elev,
    )


# --- 1. State-Machine & Parsing Unit Tests (Synthetic Events) ---


def test_parse_access_events_standard_pass() -> None:
    """Verify parsing of a standard Rise -> Culmination -> Set pass."""
    t0 = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 26, 1, 0, 0, tzinfo=timezone.utc)

    t_rise = t0 + timedelta(minutes=10)
    t_culm = t0 + timedelta(minutes=15)
    t_set = t0 + timedelta(minutes=20)

    windows = parse_access_events(
        satellite_id="SAT-01",
        ground_station_id="GS-01",
        minimum_elevation_deg=10.0,
        start_time_utc=t0,
        end_time_utc=t1,
        initial_elevation_deg=-20.0,  # Out of view at t0
        event_times_utc=[t_rise, t_culm, t_set],
        event_codes=[0, 1, 2],
        event_elevations_deg=[None, 45.2, None],
    )

    assert len(windows) == 1
    w = windows[0]
    assert isinstance(w, AccessWindow)
    assert w.satellite_id == "SAT-01"
    assert w.ground_station_id == "GS-01"
    assert w.start_time_utc == t_rise
    assert w.end_time_utc == t_set
    assert w.duration_seconds == 600.0
    assert w.culmination_time_utc == t_culm
    assert w.maximum_elevation_deg == 45.2
    assert w.minimum_elevation_deg == 10.0


def test_parse_access_events_initially_visible_clipped() -> None:
    """Verify pass where satellite is already above horizon at analysis start."""
    t0 = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 26, 1, 0, 0, tzinfo=timezone.utc)

    t_culm = t0 + timedelta(minutes=5)
    t_set = t0 + timedelta(minutes=10)

    windows = parse_access_events(
        satellite_id="SAT-01",
        ground_station_id="GS-01",
        minimum_elevation_deg=10.0,
        start_time_utc=t0,
        end_time_utc=t1,
        initial_elevation_deg=15.0,  # In view at t0
        event_times_utc=[t_culm, t_set],
        event_codes=[1, 2],
        event_elevations_deg=[35.0, None],
    )

    assert len(windows) == 1
    w = windows[0]
    assert w.start_time_utc == t0  # Clipped at analysis start
    assert w.end_time_utc == t_set
    assert w.duration_seconds == 600.0
    assert w.culmination_time_utc == t_culm
    assert w.maximum_elevation_deg == 35.0


def test_parse_access_events_interval_end_clipped() -> None:
    """Verify pass where satellite rises and remains visible past analysis end."""
    t0 = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 26, 1, 0, 0, tzinfo=timezone.utc)

    t_rise = t0 + timedelta(minutes=50)
    t_culm = t0 + timedelta(minutes=55)

    windows = parse_access_events(
        satellite_id="SAT-01",
        ground_station_id="GS-01",
        minimum_elevation_deg=10.0,
        start_time_utc=t0,
        end_time_utc=t1,
        initial_elevation_deg=-10.0,
        event_times_utc=[t_rise, t_culm],
        event_codes=[0, 1],
        event_elevations_deg=[None, 25.0],
    )

    assert len(windows) == 1
    w = windows[0]
    assert w.start_time_utc == t_rise
    assert w.end_time_utc == t1  # Clipped at analysis end
    assert w.duration_seconds == 600.0
    assert w.culmination_time_utc == t_culm
    assert w.maximum_elevation_deg == 25.0


def test_parse_access_events_visible_throughout_complete_interval() -> None:
    """Verify pass where satellite remains visible throughout entire interval with no events."""
    t0 = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 26, 1, 0, 0, tzinfo=timezone.utc)

    windows = parse_access_events(
        satellite_id="SAT-01",
        ground_station_id="GS-01",
        minimum_elevation_deg=10.0,
        start_time_utc=t0,
        end_time_utc=t1,
        initial_elevation_deg=30.0,  # Above horizon
        event_times_utc=[],
        event_codes=[],
        event_elevations_deg=[],
    )

    assert len(windows) == 1
    w = windows[0]
    assert w.start_time_utc == t0
    assert w.end_time_utc == t1
    assert w.duration_seconds == 3600.0
    assert w.culmination_time_utc is None
    assert w.maximum_elevation_deg is None


def test_parse_access_events_valid_no_access() -> None:
    """Verify that zero events and below-horizon initial elevation returns empty tuple ()."""
    t0 = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 26, 1, 0, 0, tzinfo=timezone.utc)

    windows = parse_access_events(
        satellite_id="SAT-01",
        ground_station_id="GS-01",
        minimum_elevation_deg=10.0,
        start_time_utc=t0,
        end_time_utc=t1,
        initial_elevation_deg=-30.0,
        event_times_utc=[],
        event_codes=[],
    )

    assert windows == ()


def test_parse_access_events_multiple_culminations_selects_highest() -> None:
    """Verify that multiple culminations within a pass retain the highest elevation."""
    t0 = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 26, 1, 0, 0, tzinfo=timezone.utc)

    t_rise = t0 + timedelta(minutes=5)
    t_culm1 = t0 + timedelta(minutes=10)
    t_culm2 = t0 + timedelta(minutes=15)  # Higher
    t_culm3 = t0 + timedelta(minutes=18)
    t_set = t0 + timedelta(minutes=25)

    windows = parse_access_events(
        satellite_id="SAT-01",
        ground_station_id="GS-01",
        minimum_elevation_deg=10.0,
        start_time_utc=t0,
        end_time_utc=t1,
        initial_elevation_deg=-20.0,
        event_times_utc=[t_rise, t_culm1, t_culm2, t_culm3, t_set],
        event_codes=[0, 1, 1, 1, 2],
        event_elevations_deg=[None, 30.0, 55.5, 40.0, None],
    )

    assert len(windows) == 1
    w = windows[0]
    assert w.culmination_time_utc == t_culm2
    assert w.maximum_elevation_deg == 55.5


def test_parse_access_events_malformed_sequence_errors() -> None:
    """Verify rejection of inconsistent event sequences."""
    t0 = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 26, 1, 0, 0, tzinfo=timezone.utc)

    # Mismatched lengths
    with pytest.raises(AccessEventSequenceError, match="Event count mismatch"):
        parse_access_events(
            "SAT-01", "GS-01", 10.0, t0, t1, -10.0, [t0], [0, 1]
        )

    # Culmination without elevation
    with pytest.raises(AccessEventSequenceError, match="lacks evaluated elevation"):
        parse_access_events(
            "SAT-01", "GS-01", 10.0, t0, t1, 20.0, [t0 + timedelta(minutes=5)], [1], [None]
        )

    # Duplicate rise (rise while already in view)
    with pytest.raises(AccessEventSequenceError, match="Unexpected rise event"):
        parse_access_events(
            "SAT-01",
            "GS-01",
            10.0,
            t0,
            t1,
            -10.0,
            [t0 + timedelta(minutes=5), t0 + timedelta(minutes=10)],
            [0, 0],
            [None, None],
        )

    # Set without rise
    with pytest.raises(AccessEventSequenceError, match="Unexpected set event"):
        parse_access_events(
            "SAT-01",
            "GS-01",
            10.0,
            t0,
            t1,
            -10.0,
            [t0 + timedelta(minutes=5)],
            [2],
            [None],
        )


# --- 2. Adapter & Skyfield Geometric Calculation Tests ---


def test_skyfield_earth_satellite_construction_from_satrec() -> None:
    """Verify direct construction of EarthSatellite from our initialized Satrec."""
    sat_cfg = _sample_satellite_config()
    epoch = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)
    sat_rec = create_sgp4_satellite(sat_cfg, epoch)

    ts = load.timescale(builtin=True)
    earth_sat = EarthSatellite.from_satrec(sat_rec.satrec, ts)

    assert isinstance(earth_sat, EarthSatellite)
    # Underlying Satrec is the exact same instance referenced by .model
    assert earth_sat.model is sat_rec.satrec


def test_wgs84_station_coordinates_mapping() -> None:
    """Verify mapping of ground station configuration to Skyfield GeographicPosition."""
    gs_cfg = GroundStationConfig(
        station_id="GS-TEST",
        latitude_deg=52.5,
        longitude_deg=13.4,
        altitude_m=120.0,
        minimum_elevation_deg=10.0,
    )
    pos = wgs84.latlon(
        latitude_degrees=gs_cfg.latitude_deg,
        longitude_degrees=gs_cfg.longitude_deg,
        elevation_m=gs_cfg.altitude_m,
    )
    assert pos.latitude.degrees == pytest.approx(52.5)
    assert pos.longitude.degrees == pytest.approx(13.4)
    assert pos.elevation.m == pytest.approx(120.0)


def test_calculate_access_windows_smoke_01_invariants() -> None:
    """Verify access window structural contracts on smoke_01."""
    sat_cfg = _sample_satellite_config()
    gs_cfg = _sample_station_config()
    t0 = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 26, 6, 0, 0, tzinfo=timezone.utc)

    sat_rec = create_sgp4_satellite(sat_cfg, t0)
    windows = calculate_access_windows(sat_rec, gs_cfg, t0, t1)

    assert isinstance(windows, tuple)
    for i, w in enumerate(windows):
        assert isinstance(w, AccessWindow)
        assert w.satellite_id == "SAT-SMOKE-01"
        assert w.ground_station_id == "GS-SMOKE-01"
        assert w.minimum_elevation_deg == 10.0
        assert w.start_time_utc.tzinfo is not None
        assert w.end_time_utc.tzinfo is not None
        assert w.start_time_utc.utcoffset() == timedelta(0)
        assert w.end_time_utc.utcoffset() == timedelta(0)

        # Boundary and positive duration contracts
        assert w.duration_seconds > 0.0
        assert t0 <= w.start_time_utc < w.end_time_utc <= t1
        assert (w.end_time_utc - w.start_time_utc).total_seconds() == pytest.approx(
            w.duration_seconds, abs=1e-6
        )

        # Culmination check
        if w.culmination_time_utc is not None:
            assert w.start_time_utc <= w.culmination_time_utc <= w.end_time_utc
            assert w.maximum_elevation_deg is not None
            assert w.maximum_elevation_deg >= w.minimum_elevation_deg

        # Chronological ordering and no overlap
        if i > 0:
            prev_w = windows[i - 1]
            assert w.start_time_utc >= prev_w.end_time_utc


def test_threshold_monotonicity() -> None:
    """Invariant test: Total access duration at 5 deg >= 10 deg >= 20 deg."""
    sat_cfg = _sample_satellite_config()
    t0 = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 26, 6, 0, 0, tzinfo=timezone.utc)
    sat_rec = create_sgp4_satellite(sat_cfg, t0)

    windows_5 = calculate_access_windows(sat_rec, _sample_station_config(5.0), t0, t1)
    windows_10 = calculate_access_windows(sat_rec, _sample_station_config(10.0), t0, t1)
    windows_20 = calculate_access_windows(sat_rec, _sample_station_config(20.0), t0, t1)

    total_5 = sum(w.duration_seconds for w in windows_5)
    total_10 = sum(w.duration_seconds for w in windows_10)
    total_20 = sum(w.duration_seconds for w in windows_20)

    # Lower elevation threshold must strictly yield >= total access duration
    assert total_5 >= total_10
    assert total_10 >= total_20


def test_calculate_access_windows_deterministic() -> None:
    """Verify that repeated calculation in the same environment produces identical windows."""
    sat_cfg = _sample_satellite_config()
    gs_cfg = _sample_station_config()
    t0 = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 26, 6, 0, 0, tzinfo=timezone.utc)
    sat_rec = create_sgp4_satellite(sat_cfg, t0)

    windows1 = calculate_access_windows(sat_rec, gs_cfg, t0, t1)
    windows2 = calculate_access_windows(sat_rec, gs_cfg, t0, t1)

    assert len(windows1) == len(windows2)
    for w1, w2 in zip(windows1, windows2):
        assert w1 == w2


def test_no_file_system_side_effects(tmp_path: Path) -> None:
    """Verify that calculate_access_windows performs zero disk I/O or directory creation."""
    sat_cfg = _sample_satellite_config()
    gs_cfg = _sample_station_config()
    t0 = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 26, 6, 0, 0, tzinfo=timezone.utc)
    sat_rec = create_sgp4_satellite(sat_cfg, t0)

    # Snapshot directory before
    contents_before = list(tmp_path.iterdir())
    calculate_access_windows(sat_rec, gs_cfg, t0, t1)
    contents_after = list(tmp_path.iterdir())

    assert contents_before == contents_after


def test_end_to_end_smoke_01_access() -> None:
    """Integration test: Load scenarios/smoke_01.yaml and calculate access windows."""
    yaml_path = Path(__file__).resolve().parent.parent / "scenarios" / "smoke_01.yaml"
    scenario = load_scenario(yaml_path)

    sat_rec = create_sgp4_satellite(scenario.satellites[0], scenario.analysis.start_time_utc)
    station = scenario.ground_stations[0]
    t0 = scenario.analysis.start_time_utc
    t1 = scenario.analysis.end_time_utc

    windows = calculate_access_windows(
        satellite_record=sat_rec,
        ground_station=station,
        start_time_utc=t0,
        end_time_utc=t1,
    )

    # Contract assertions per Stage 1 requirements
    assert isinstance(windows, tuple)
    assert len(windows) >= 1  # At least one access window is returned

    has_culmination = False
    has_max_elev_above_threshold = False

    for i, w in enumerate(windows):
        assert isinstance(w, AccessWindow)
        assert w.satellite_id == "SAT-SMOKE-01"
        assert w.ground_station_id == "GS-SMOKE-01"
        assert w.minimum_elevation_deg == 10.0

        # Positive duration and within analysis interval
        assert w.duration_seconds > 0.0
        assert t0 <= w.start_time_utc < w.end_time_utc <= t1
        assert (w.end_time_utc - w.start_time_utc).total_seconds() == pytest.approx(
            w.duration_seconds, abs=1e-6
        )

        # Check culmination and elevation properties
        if w.culmination_time_utc is not None:
            has_culmination = True
            assert w.start_time_utc <= w.culmination_time_utc <= w.end_time_utc
            assert w.maximum_elevation_deg is not None
            if w.maximum_elevation_deg > station.minimum_elevation_deg:
                has_max_elev_above_threshold = True

        # Chronological ordering and no overlap
        if i > 0:
            prev_w = windows[i - 1]
            assert w.start_time_utc >= prev_w.end_time_utc

    assert has_culmination
    assert has_max_elev_above_threshold
