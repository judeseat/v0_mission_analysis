"""Unit, contract, and invariant tests for time-grid generation and propagation (Stage 1 Task 4).

Note on testing scope:
    Numerical checks in this module test internal consistency, data contracts, and
    broad physical bounds. They do not constitute independent orbital validation.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pytest

from v0_tool.config import AnalysisConfig, SatelliteConfig, load_scenario
from v0_tool.propagation import (
    EphemerisProduct,
    Sgp4PropagationError,
    _check_sgp4_errors,
    datetimes_to_split_jd,
    generate_time_grid,
    propagate_satellite,
)
from v0_tool.sgp4_adapter import create_sgp4_satellite


def _sample_analysis_config() -> AnalysisConfig:
    """Return the smoke_01 analysis configuration: 6 hours at 300 s steps."""
    return AnalysisConfig(
        start_time_utc=datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc),
        end_time_utc=datetime(2026, 10, 26, 6, 0, 0, tzinfo=timezone.utc),
        ephemeris_interval_seconds=300.0,
    )


def _sample_satellite_config() -> SatelliteConfig:
    """Return the smoke_01 satellite configuration."""
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


# --- 1. Time-Grid Tests ---


def test_time_grid_smoke_01_sample_count_and_endpoints() -> None:
    """Verify that smoke_01 produces exactly 73 inclusive samples spanning start to end."""
    analysis = _sample_analysis_config()
    grid = generate_time_grid(analysis)

    assert isinstance(grid, np.ndarray)
    assert grid.ndim == 1
    assert grid.dtype == object
    assert len(grid) == 73

    # Exact boundary inclusions
    assert grid[0] == datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)
    assert grid[-1] == datetime(2026, 10, 26, 6, 0, 0, tzinfo=timezone.utc)


def test_time_grid_monotonic_interval() -> None:
    """Verify that consecutive samples are separated by exactly 300 seconds."""
    analysis = _sample_analysis_config()
    grid = generate_time_grid(analysis)

    expected_delta = timedelta(seconds=300.0)
    for i in range(len(grid) - 1):
        actual_delta = grid[i + 1] - grid[i]
        assert actual_delta == expected_delta


def test_time_grid_rejects_non_integer_multiple() -> None:
    """Verify ValueError when analysis duration is not divisible by interval."""
    # Duration = 1000s, interval = 300s -> remainder 100s
    analysis = AnalysisConfig(
        start_time_utc=datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc),
        end_time_utc=datetime(2026, 10, 26, 0, 16, 40, tzinfo=timezone.utc),
        ephemeris_interval_seconds=300.0,
    )
    with pytest.raises(ValueError, match="must be an integer multiple"):
        generate_time_grid(analysis)


def test_time_grid_deterministic() -> None:
    """Verify repeated time-grid generation yields identical arrays."""
    analysis = _sample_analysis_config()
    grid1 = generate_time_grid(analysis)
    grid2 = generate_time_grid(analysis)
    assert np.array_equal(grid1, grid2)


def test_datetimes_to_split_jd() -> None:
    """Verify split Julian Date array generation."""
    grid = np.array(
        [
            datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc),
        ],
        dtype=object,
    )
    jd_arr, fr_arr = datetimes_to_split_jd(grid)

    assert jd_arr.shape == (2,)
    assert fr_arr.shape == (2,)
    assert jd_arr.dtype == np.float64
    assert fr_arr.dtype == np.float64

    # 2026-10-26 00:00:00 UTC -> JD 2461339.5
    assert jd_arr[0] + fr_arr[0] == pytest.approx(2461339.5, abs=1e-9)
    # 2026-10-26 12:00:00 UTC -> JD 2461340.0
    assert jd_arr[1] + fr_arr[1] == pytest.approx(2461340.0, abs=1e-9)


# --- 2. Propagation Input Validation Tests ---


def test_propagate_satellite_rejects_invalid_timestamps() -> None:
    """Verify timestamp array contract validation in propagate_satellite."""
    sat = _sample_satellite_config()
    epoch = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)
    rec = create_sgp4_satellite(sat, epoch)

    # Empty array
    with pytest.raises(ValueError, match="must not be empty"):
        propagate_satellite(rec, np.array([], dtype=object))

    # 2D array
    with pytest.raises(ValueError, match="must be 1-dimensional"):
        propagate_satellite(rec, np.empty((2, 2), dtype=object))

    # Non-datetime object
    with pytest.raises(ValueError, match="is not a datetime"):
        propagate_satellite(rec, np.array(["2026-10-26T00:00:00Z"], dtype=object))

    # Naive datetime
    naive_grid = np.array([datetime(2026, 10, 26, 0, 0, 0)], dtype=object)
    with pytest.raises(ValueError, match="must be timezone-aware"):
        propagate_satellite(rec, naive_grid)

    # Non-UTC offset (+02:00)
    offset_grid = np.array(
        [datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone(timedelta(hours=2)))],
        dtype=object,
    )
    with pytest.raises(ValueError, match="must have UTC offset"):
        propagate_satellite(rec, offset_grid)

    # Non-increasing / duplicate timestamps
    duplicate_grid = np.array(
        [
            datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc),
        ],
        dtype=object,
    )
    with pytest.raises(ValueError, match="strictly increasing"):
        propagate_satellite(rec, duplicate_grid)

    # Decreasing timestamps
    decreasing_grid = np.array(
        [
            datetime(2026, 10, 26, 0, 5, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc),
        ],
        dtype=object,
    )
    with pytest.raises(ValueError, match="strictly increasing"):
        propagate_satellite(rec, decreasing_grid)


# --- 3. Propagation Execution and Contract Tests ---


def test_propagate_smoke_01_contracts_and_types() -> None:
    """Verify EphemerisProduct array contracts, dtypes, metadata, and zero errors for smoke_01."""
    sat_cfg = _sample_satellite_config()
    analysis = _sample_analysis_config()
    rec = create_sgp4_satellite(sat_cfg, analysis.start_time_utc)
    grid = generate_time_grid(analysis)

    eph = propagate_satellite(rec, grid)

    # Provenance and metadata
    assert isinstance(eph, EphemerisProduct)
    assert eph.satellite_id == "SAT-SMOKE-01"
    assert eph.frame == "TEME"
    assert eph.position_unit == "km"
    assert eph.velocity_unit == "km/s"
    assert eph.propagation_model == "SGP4"
    assert eph.gravity_model == "WGS72"

    # Array shapes
    assert eph.timestamps_utc.shape == (73,)
    assert eph.position_teme_km.shape == (73, 3)
    assert eph.velocity_teme_km_s.shape == (73, 3)
    assert eph.sgp4_error_codes.shape == (73,)

    # Array dtypes
    assert eph.timestamps_utc.dtype == object
    assert eph.position_teme_km.dtype == np.float64
    assert eph.velocity_teme_km_s.dtype == np.float64
    assert np.issubdtype(eph.sgp4_error_codes.dtype, np.integer)

    # All SGP4 error codes equal zero
    assert np.all(eph.sgp4_error_codes == 0)

    # All values are finite
    assert np.all(np.isfinite(eph.position_teme_km))
    assert np.all(np.isfinite(eph.velocity_teme_km_s))


def test_propagate_first_state_epoch_and_physical_bounds() -> None:
    """Verify initial epoch state correspondence and broad physical bounds across all samples."""
    sat_cfg = _sample_satellite_config()
    analysis = _sample_analysis_config()
    rec = create_sgp4_satellite(sat_cfg, analysis.start_time_utc)
    grid = generate_time_grid(analysis)

    eph = propagate_satellite(rec, grid)

    # First state correspondence at t = 0 (analysis.start_time_utc)
    assert eph.timestamps_utc[0] == analysis.start_time_utc
    r0 = np.linalg.norm(eph.position_teme_km[0])
    v0 = np.linalg.norm(eph.velocity_teme_km_s[0])

    # Broad physical bounds:
    # 6500 km < radius < 7500 km
    # 6.0 km/s < speed < 9.0 km/s
    assert 6500.0 < r0 < 7500.0
    assert 6.0 < v0 < 9.0

    # Check bounds across the entire 6-hour trajectory
    radii = np.linalg.norm(eph.position_teme_km, axis=1)
    speeds = np.linalg.norm(eph.velocity_teme_km_s, axis=1)

    assert np.all((radii > 6500.0) & (radii < 7500.0))
    assert np.all((speeds > 6.0) & (speeds < 9.0))


def test_propagate_deterministic_repeated() -> None:
    """Verify that repeated propagation in the same environment produces exact equality."""
    sat_cfg = _sample_satellite_config()
    analysis = _sample_analysis_config()
    rec = create_sgp4_satellite(sat_cfg, analysis.start_time_utc)
    grid = generate_time_grid(analysis)

    eph1 = propagate_satellite(rec, grid)
    eph2 = propagate_satellite(rec, grid)

    assert np.array_equal(eph1.position_teme_km, eph2.position_teme_km)
    assert np.array_equal(eph1.velocity_teme_km_s, eph2.velocity_teme_km_s)
    assert np.array_equal(eph1.sgp4_error_codes, eph2.sgp4_error_codes)


def test_sgp4_error_handling_synthetic() -> None:
    """Verify error processing helper raises Sgp4PropagationError on non-zero codes."""
    grid = np.array(
        [
            datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 26, 0, 5, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 26, 0, 10, 0, tzinfo=timezone.utc),
        ],
        dtype=object,
    )
    # Inject synthetic error code 6 (decayed satellite) at index 1
    synthetic_errors = np.array([0, 6, 0], dtype=np.int32)

    with pytest.raises(Sgp4PropagationError) as exc_info:
        _check_sgp4_errors("SAT-TEST", grid, synthetic_errors)

    err_msg = str(exc_info.value)
    assert "SAT-TEST" in err_msg
    assert "index 1" in err_msg
    assert "2026-10-26 00:05:00+00:00" in err_msg
    assert "Code 6" in err_msg


def test_end_to_end_from_smoke_01_yaml() -> None:
    """Integration test: Load scenarios/smoke_01.yaml and propagate to EphemerisProduct."""
    yaml_path = Path(__file__).resolve().parent.parent / "scenarios" / "smoke_01.yaml"
    scenario = load_scenario(yaml_path)

    sat_cfg = scenario.satellites[0]
    rec = create_sgp4_satellite(sat_cfg, scenario.analysis.start_time_utc)
    grid = generate_time_grid(scenario.analysis)
    eph = propagate_satellite(rec, grid)

    assert eph.satellite_id == "SAT-SMOKE-01"
    assert len(eph.timestamps_utc) == 73
    assert eph.position_teme_km.shape == (73, 3)
    assert np.all(eph.sgp4_error_codes == 0)
