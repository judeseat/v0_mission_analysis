"""Constellation generation functions for synthetic satellite constellations.

Selected V0 Walker Delta convention:
    internal plane index:
        p = 0, ..., P - 1
    internal slot index:
        s = 0, ..., S - 1
    satellites per plane:
        S = T / P
    RAAN:
        raan_deg = (raan_origin_deg + p * 360 / P) % 360
    mean anomaly:
        mean_anomaly_deg = (
            mean_anomaly_origin_deg
            + s * 360 / S
            + p * phasing * 360 / T
        ) % 360

    Increasing plane index produces a positive phase offset.
    Note: This is the selected V0 Walker Delta convention and is not described
    as universal across every tool or reference.
"""

from v0_tool.config import SatelliteConfig, WalkerDeltaConfig


def generate_walker_delta(config: WalkerDeltaConfig) -> tuple[SatelliteConfig, ...]:
    """Generate discrete SatelliteConfig records from a Walker Delta definition.

    Generates satellites in deterministic plane-major order with IDs formatted as:
        SAT-P{p+1:02d}-S{s+1:02d}

    Args:
        config: Validated WalkerDeltaConfig.

    Returns:
        tuple[SatelliteConfig, ...]: Chronologically and hierarchically ordered
            satellite configuration records.
    """
    total_satellites = config.total_satellites
    planes = config.planes
    phasing = config.phasing
    satellites_per_plane = total_satellites // planes

    generated: list[SatelliteConfig] = []

    for p in range(planes):
        raan_deg = (config.raan_origin_deg + p * 360.0 / planes) % 360.0

        for s in range(satellites_per_plane):
            sat_id = f"SAT-P{p + 1:02d}-S{s + 1:02d}"

            mean_anomaly_deg = (
                config.mean_anomaly_origin_deg
                + s * 360.0 / satellites_per_plane
                + p * phasing * 360.0 / total_satellites
            ) % 360.0

            satellite = SatelliteConfig(
                satellite_id=sat_id,
                altitude_km=config.altitude_km,
                inclination_deg=config.inclination_deg,
                eccentricity=config.eccentricity,
                raan_deg=raan_deg,
                arg_perigee_deg=config.arg_perigee_deg,
                mean_anomaly_deg=mean_anomaly_deg,
                bstar=config.bstar,
            )
            generated.append(satellite)

    return tuple(generated)
