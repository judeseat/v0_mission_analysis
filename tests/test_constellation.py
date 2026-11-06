"""Unit tests for synthetic Walker Delta constellation generation (Stage 2 Task 1)."""

import pytest

from v0_tool.config import SatelliteConfig, WalkerDeltaConfig
from v0_tool.constellation import generate_walker_delta


@pytest.fixture
def walker_6_2_1_config() -> WalkerDeltaConfig:
    """Standard POC-01 Walker Delta 6/2/1 configuration."""
    return WalkerDeltaConfig(
        constellation_id="WALKER-6-2-1",
        total_satellites=6,
        planes=2,
        phasing=1,
        altitude_km=550.0,
        inclination_deg=53.0,
        eccentricity=0.0,
        raan_origin_deg=0.0,
        mean_anomaly_origin_deg=0.0,
        arg_perigee_deg=0.0,
        bstar=0.0,
    )


def test_generate_walker_delta_6_2_1_exact_table(walker_6_2_1_config: WalkerDeltaConfig) -> None:
    """Verify exact 6-satellite output, IDs, ordering, RAAN and mean anomalies for 6/2/1.

    Expected table:
      P01-S01: RAAN 0.0, M 0.0
      P01-S02: RAAN 0.0, M 120.0
      P01-S03: RAAN 0.0, M 240.0
      P02-S01: RAAN 180.0, M 60.0
      P02-S02: RAAN 180.0, M 180.0
      P02-S03: RAAN 180.0, M 300.0
    """
    sats = generate_walker_delta(walker_6_2_1_config)

    assert isinstance(sats, tuple)
    assert len(sats) == 6

    expected_data = [
        ("SAT-P01-S01", 0.0, 0.0),
        ("SAT-P01-S02", 0.0, 120.0),
        ("SAT-P01-S03", 0.0, 240.0),
        ("SAT-P02-S01", 180.0, 60.0),
        ("SAT-P02-S02", 180.0, 180.0),
        ("SAT-P02-S03", 180.0, 300.0),
    ]

    for sat, (exp_id, exp_raan, exp_m) in zip(sats, expected_data):
        assert isinstance(sat, SatelliteConfig)
        assert sat.satellite_id == exp_id
        assert sat.raan_deg == pytest.approx(exp_raan, abs=1e-9)
        assert sat.mean_anomaly_deg == pytest.approx(exp_m, abs=1e-9)
        # Check common parameters
        assert sat.altitude_km == 550.0
        assert sat.inclination_deg == 53.0
        assert sat.eccentricity == 0.0
        assert sat.arg_perigee_deg == 0.0
        assert sat.bstar == 0.0


def test_walker_spacing_and_phase_offset(walker_6_2_1_config: WalkerDeltaConfig) -> None:
    """Verify 120-deg in-plane spacing and 60-deg plane-to-plane phase offset."""
    sats = generate_walker_delta(walker_6_2_1_config)

    # In-plane spacing for Plane 1
    assert sats[1].mean_anomaly_deg - sats[0].mean_anomaly_deg == pytest.approx(120.0)
    assert sats[2].mean_anomaly_deg - sats[1].mean_anomaly_deg == pytest.approx(120.0)

    # In-plane spacing for Plane 2
    assert sats[4].mean_anomaly_deg - sats[3].mean_anomaly_deg == pytest.approx(120.0)
    assert sats[5].mean_anomaly_deg - sats[4].mean_anomaly_deg == pytest.approx(120.0)

    # Plane-to-plane phase offset between slot 0 of Plane 1 and slot 0 of Plane 2
    assert sats[3].mean_anomaly_deg - sats[0].mean_anomaly_deg == pytest.approx(60.0)


def test_walker_angle_normalization_non_zero_origins() -> None:
    """Verify normalization [0, 360) with non-zero origins."""
    cfg = WalkerDeltaConfig(
        constellation_id="WALKER-OFFSET",
        total_satellites=6,
        planes=2,
        phasing=1,
        altitude_km=550.0,
        inclination_deg=53.0,
        raan_origin_deg=350.0,
        mean_anomaly_origin_deg=300.0,
    )
    sats = generate_walker_delta(cfg)

    # P01: raan = 350.0
    # P02: raan = (350 + 180) % 360 = 170.0
    assert sats[0].raan_deg == pytest.approx(350.0)
    assert sats[3].raan_deg == pytest.approx(170.0)

    # Check all angles strictly within [0, 360)
    for sat in sats:
        assert 0.0 <= sat.raan_deg < 360.0
        assert 0.0 <= sat.mean_anomaly_deg < 360.0

    # P01-S01: M = 300 % 360 = 300
    # P01-S02: M = (300 + 120) % 360 = 60
    # P01-S03: M = (300 + 240) % 360 = 180
    assert sats[0].mean_anomaly_deg == pytest.approx(300.0)
    assert sats[1].mean_anomaly_deg == pytest.approx(60.0)
    assert sats[2].mean_anomaly_deg == pytest.approx(180.0)


def test_walker_repeated_generation_equality(walker_6_2_1_config: WalkerDeltaConfig) -> None:
    """Verify deterministic repeated generation gives equal definitions."""
    sats1 = generate_walker_delta(walker_6_2_1_config)
    sats2 = generate_walker_delta(walker_6_2_1_config)
    assert sats1 == sats2


def test_walker_validation_divisibility() -> None:
    """Verify rejection when total_satellites is not divisible by planes."""
    with pytest.raises(ValueError, match="must be divisible by planes"):
        WalkerDeltaConfig(
            constellation_id="W-BAD",
            total_satellites=7,
            planes=2,
            phasing=1,
            altitude_km=550.0,
            inclination_deg=53.0,
        )


def test_walker_validation_phasing() -> None:
    """Verify rejection when phasing parameter F >= planes P."""
    # F == P (1 == 1) rejected
    with pytest.raises(ValueError, match="must be strictly less than planes"):
        WalkerDeltaConfig(
            constellation_id="W-BAD-PHASE",
            total_satellites=6,
            planes=2,
            phasing=2,
            altitude_km=550.0,
            inclination_deg=53.0,
        )

    # F > P rejected
    with pytest.raises(ValueError, match="must be strictly less than planes"):
        WalkerDeltaConfig(
            constellation_id="W-BAD-PHASE",
            total_satellites=6,
            planes=2,
            phasing=3,
            altitude_km=550.0,
            inclination_deg=53.0,
        )


def test_walker_validation_invalid_counts_and_angles() -> None:
    """Verify rejection of non-positive counts and out-of-range orbital parameters."""
    # Non-positive total_satellites
    with pytest.raises(ValueError):
        WalkerDeltaConfig(
            constellation_id="W",
            total_satellites=0,
            planes=1,
            phasing=0,
            altitude_km=550.0,
            inclination_deg=53.0,
        )

    # Non-positive planes
    with pytest.raises(ValueError):
        WalkerDeltaConfig(
            constellation_id="W",
            total_satellites=6,
            planes=0,
            phasing=0,
            altitude_km=550.0,
            inclination_deg=53.0,
        )

    # Empty constellation_id
    with pytest.raises(ValueError, match="constellation_id must be a non-empty string"):
        WalkerDeltaConfig(
            constellation_id="   ",
            total_satellites=6,
            planes=2,
            phasing=1,
            altitude_km=550.0,
            inclination_deg=53.0,
        )

    # Invalid inclination
    with pytest.raises(ValueError):
        WalkerDeltaConfig(
            constellation_id="W",
            total_satellites=6,
            planes=2,
            phasing=1,
            altitude_km=550.0,
            inclination_deg=185.0,
        )
