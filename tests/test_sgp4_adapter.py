"""Unit and equation tests for the SGP4 adapter (Stage 1 Task 3).

Note on testing scope:
    Numerical comparisons in this module verify the internal consistency, equation
    implementations, and unit conversions against the exact analytical equations and
    the SGP4 package constants. They are equation and unit tests, not external or
    independent orbit-truth validation.
"""

from datetime import datetime, timezone, timedelta
import math
from pathlib import Path

import pytest
import sgp4.api
import sgp4.earth_gravity

from v0_tool.config import SatelliteConfig, load_scenario
from v0_tool.sgp4_adapter import (
    GRAVITY_MODELS,
    Sgp4SatelliteRecord,
    create_sgp4_satellite,
    datetime_to_sgp4_epoch,
    design_altitude_to_mean_motion,
)


def _sample_satellite_config() -> SatelliteConfig:
    """Return a representative circular design satellite configuration."""
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


def test_wgs72_mean_motion_equation() -> None:
    """Equation test: Verify altitude-to-mean-motion conversion against WGS72 constants.

    Uses constants directly from sgp4.earth_gravity.wgs72:
        radiusearthkm = 6378.135
        mu = 398600.8
    """
    wgs72 = sgp4.earth_gravity.wgs72
    h = 550.0

    # Analytical equation derivation
    expected_a = wgs72.radiusearthkm + h  # 6928.135 km
    expected_n_s = math.sqrt(wgs72.mu / (expected_a**3))  # rad/s
    expected_no_kozai = expected_n_s * 60.0  # rad/min
    expected_period_s = 2.0 * math.pi / expected_n_s  # s

    # Verify helper function
    computed_no_kozai = design_altitude_to_mean_motion(
        altitude_km=h,
        earth_radius_km=wgs72.radiusearthkm,
        mu_km3_s2=wgs72.mu,
    )
    assert computed_no_kozai == pytest.approx(expected_no_kozai, rel=1e-12)

    # Reference numerical checks for WGS72 at 550 km
    assert expected_a == 6928.135
    assert computed_no_kozai == pytest.approx(0.0656894795335, rel=1e-9)
    assert expected_period_s == pytest.approx(5738.98775, rel=1e-6)
    assert (expected_period_s / 60.0) == pytest.approx(95.6498, rel=1e-5)


def test_design_altitude_to_mean_motion_invalid() -> None:
    """Verify rejection of zero, negative, or unphysical altitudes in helper."""
    wgs72 = sgp4.earth_gravity.wgs72
    with pytest.raises(ValueError, match="altitude_km must be positive"):
        design_altitude_to_mean_motion(0.0, wgs72.radiusearthkm, wgs72.mu)

    with pytest.raises(ValueError, match="altitude_km must be positive"):
        design_altitude_to_mean_motion(-100.0, wgs72.radiusearthkm, wgs72.mu)


def test_datetime_to_sgp4_epoch() -> None:
    """Verify SGP4 epoch calculation and offset from reference Julian Date.

    Reference: 2026-10-26 00:00:00 UTC
    Julian Date is 2461339.5.
    Epoch offset base (1949-12-31 00:00:00 UTC) is 2433281.5.
    Expected epoch_days = 2461339.5 - 2433281.5 = 28058.0 days.
    """
    dt = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)
    epoch_days, jd, fr = datetime_to_sgp4_epoch(dt)

    assert jd + fr == pytest.approx(2461339.5, abs=1e-9)
    assert epoch_days == pytest.approx(28058.0, abs=1e-9)


def test_datetime_to_sgp4_epoch_rejection() -> None:
    """Verify rejection of naive datetimes and non-UTC offsets in epoch conversion."""
    # Naive datetime
    naive_dt = datetime(2026, 10, 26, 0, 0, 0)
    with pytest.raises(ValueError, match="epoch_utc must be timezone-aware"):
        datetime_to_sgp4_epoch(naive_dt)

    # Non-UTC offset (+01:00)
    offset_dt = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone(timedelta(hours=1)))
    with pytest.raises(ValueError, match="epoch_utc must have UTC timezone"):
        datetime_to_sgp4_epoch(offset_dt)


def test_create_sgp4_satellite_wgs72_default() -> None:
    """Verify default WGS72 initialization of Sgp4SatelliteRecord."""
    sat_cfg = _sample_satellite_config()
    epoch_utc = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)

    record = create_sgp4_satellite(sat_cfg, epoch_utc)

    # Record wrapper attributes
    assert isinstance(record, Sgp4SatelliteRecord)
    assert record.satellite_id == "SAT-SMOKE-01"
    assert record.satnum == 1
    assert record.epoch_utc == epoch_utc
    assert record.gravity_model == "WGS72"

    # Underlying Satrec attributes
    satrec = record.satrec
    assert satrec.error == 0
    assert satrec.satnum == 1
    assert satrec.jdsatepoch == pytest.approx(2461339.5, abs=1e-9)
    assert satrec.jdsatepochF == pytest.approx(0.0, abs=1e-9)

    # WGS72 physical constants populated on Satrec
    assert satrec.radiusearthkm == pytest.approx(6378.135, abs=1e-9)
    assert satrec.mu == pytest.approx(398600.8, abs=1e-6)

    # Kozai mean motion matches WGS72 equation
    expected_no_kozai = design_altitude_to_mean_motion(
        550.0, sgp4.earth_gravity.wgs72.radiusearthkm, sgp4.earth_gravity.wgs72.mu
    )
    assert satrec.no_kozai == pytest.approx(expected_no_kozai, rel=1e-9)

    # Field mappings and zero-drag assumptions
    assert satrec.bstar == 0.0
    assert satrec.ndot == 0.0
    assert satrec.nddot == 0.0
    assert satrec.ecco == 0.0
    assert satrec.inclo == pytest.approx(math.radians(53.0), abs=1e-9)
    assert satrec.nodeo == pytest.approx(0.0, abs=1e-9)
    assert satrec.argpo == pytest.approx(0.0, abs=1e-9)
    assert satrec.mo == pytest.approx(0.0, abs=1e-9)


def test_create_sgp4_satellite_wgs84_optional() -> None:
    """Verify optional WGS84 gravity-model selection and corresponding constants."""
    sat_cfg = _sample_satellite_config()
    epoch_utc = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)

    record = create_sgp4_satellite(
        sat_cfg, epoch_utc, satnum=42, gravity_model="WGS84"
    )

    assert record.gravity_model == "WGS84"
    assert record.satnum == 42
    assert record.satrec.error == 0

    # Satrec reflects WGS84 constants
    assert record.satrec.radiusearthkm == pytest.approx(6378.137, abs=1e-9)
    assert record.satrec.mu == pytest.approx(398600.5, abs=1e-6)

    expected_no_kozai_wgs84 = design_altitude_to_mean_motion(
        550.0, sgp4.earth_gravity.wgs84.radiusearthkm, sgp4.earth_gravity.wgs84.mu
    )
    assert record.satrec.no_kozai == pytest.approx(expected_no_kozai_wgs84, rel=1e-9)


def test_angle_mappings_non_zero() -> None:
    """Verify degree-to-radian conversions for non-zero angles."""
    sat_cfg = SatelliteConfig(
        satellite_id="SAT-ANGLES",
        altitude_km=600.0,
        inclination_deg=98.2,
        eccentricity=0.001,
        raan_deg=45.5,
        arg_perigee_deg=120.25,
        mean_anomaly_deg=270.75,
        bstar=1e-5,
    )
    epoch_utc = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)
    record = create_sgp4_satellite(sat_cfg, epoch_utc)

    satrec = record.satrec
    assert satrec.error == 0
    assert satrec.ecco == pytest.approx(0.001, abs=1e-9)
    assert satrec.bstar == pytest.approx(1e-5, abs=1e-12)
    assert satrec.inclo == pytest.approx(math.radians(98.2), abs=1e-9)
    assert satrec.nodeo == pytest.approx(math.radians(45.5), abs=1e-9)
    assert satrec.argpo == pytest.approx(math.radians(120.25), abs=1e-9)
    assert satrec.mo == pytest.approx(math.radians(270.75), abs=1e-9)


def test_unsupported_gravity_model_rejection() -> None:
    """Verify rejection of unknown or unsupported gravity model names."""
    sat_cfg = _sample_satellite_config()
    epoch_utc = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="Unsupported gravity_model 'GRS80'"):
        create_sgp4_satellite(sat_cfg, epoch_utc, gravity_model="GRS80")


def test_invalid_satnum_rejection() -> None:
    """Verify rejection of non-positive, zero, float, or boolean satnum."""
    sat_cfg = _sample_satellite_config()
    epoch_utc = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)

    # Zero
    with pytest.raises(ValueError, match="satnum must be a positive integer"):
        create_sgp4_satellite(sat_cfg, epoch_utc, satnum=0)

    # Negative
    with pytest.raises(ValueError, match="satnum must be a positive integer"):
        create_sgp4_satellite(sat_cfg, epoch_utc, satnum=-5)

    # Boolean (True evaluates as int in Python if not guarded)
    with pytest.raises(ValueError, match="satnum must be a positive integer"):
        create_sgp4_satellite(sat_cfg, epoch_utc, satnum=True)  # type: ignore[arg-type]

    # Float
    with pytest.raises(ValueError, match="satnum must be a positive integer"):
        create_sgp4_satellite(sat_cfg, epoch_utc, satnum=1.5)  # type: ignore[arg-type]


def test_deterministic_repeated_construction() -> None:
    """Verify that identical inputs produce identical numerical Satrec attributes."""
    sat_cfg = _sample_satellite_config()
    epoch_utc = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)

    rec1 = create_sgp4_satellite(sat_cfg, epoch_utc, satnum=1)
    rec2 = create_sgp4_satellite(sat_cfg, epoch_utc, satnum=1)

    assert rec1.satrec.error == rec2.satrec.error == 0
    assert rec1.satrec.no_kozai == rec2.satrec.no_kozai
    assert rec1.satrec.inclo == rec2.satrec.inclo
    assert rec1.satrec.nodeo == rec2.satrec.nodeo
    assert rec1.satrec.argpo == rec2.satrec.argpo
    assert rec1.satrec.mo == rec2.satrec.mo
    assert rec1.satrec.jdsatepoch == rec2.satrec.jdsatepoch
    assert rec1.satrec.jdsatepochF == rec2.satrec.jdsatepochF


def test_load_and_convert_smoke_01_satellite() -> None:
    """Integration test: Load smoke_01.yaml and convert its satellite to SGP4 record."""
    yaml_path = Path(__file__).resolve().parent.parent / "scenarios" / "smoke_01.yaml"
    scenario = load_scenario(yaml_path)

    smoke_sat = scenario.satellites[0]
    epoch_utc = scenario.analysis.start_time_utc

    record = create_sgp4_satellite(smoke_sat, epoch_utc, satnum=1)

    assert record.satellite_id == "SAT-SMOKE-01"
    assert record.satnum == 1
    assert record.gravity_model == "WGS72"
    assert record.satrec.error == 0
    assert record.satrec.ecco == 0.0
    assert record.satrec.inclo == pytest.approx(math.radians(53.0))
