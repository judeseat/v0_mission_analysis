"""SGP4 adapter for constructing satellite records from design configurations.

Note on representative design orbits:
    The conversion of a geometric circular altitude into SGP4 mean motion (no_kozai)
    implemented here uses standard two-body Keplerian mechanics based on the Earth
    radius and gravitational parameter of the selected SGP4 gravity model.
    This is an engineering design-orbit approximation suitable for Phase A/B1
    constellation geometry and visibility analysis. It is NOT an exact conversion to
    fitted Kozai/Brouwer mean elements, and the initial propagated osculating altitude
    is not guaranteed to equal the design altitude exactly due to SGP4's internal
    short- and long-period gravitational harmonic corrections (J2, J3, J4).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import math

import sgp4.api
import sgp4.earth_gravity
from sgp4.api import Satrec, jday

from v0_tool.config import SatelliteConfig

# Internal registry mapping gravity-model identifiers to the SGP4 API selector
# and physical Earth constants from the installed sgp4 package.
GRAVITY_MODELS = {
    "WGS72": (sgp4.api.WGS72, sgp4.earth_gravity.wgs72),
    "WGS84": (sgp4.api.WGS84, sgp4.earth_gravity.wgs84),
}


@dataclass(frozen=True)
class Sgp4SatelliteRecord:
    """Library-specific record binding a satellite identifier to an initialized Satrec.

    This record is adapter-internal and preserves satellite identity, catalog number,
    UTC epoch, and gravity model selection alongside the compiled Satrec object.
    """

    satellite_id: str
    satnum: int
    satrec: Satrec
    epoch_utc: datetime
    gravity_model: str


def design_altitude_to_mean_motion(
    altitude_km: float, earth_radius_km: float, mu_km3_s2: float
) -> float:
    """Convert circular design altitude to SGP4 Kozai mean motion (rad/min).

    Uses the two-body relationship:
        semi_major_axis_km = earth_radius_km + altitude_km
        mean_motion_rad_s = sqrt(mu_km3_s2 / semi_major_axis_km**3)
        no_kozai_rad_min = mean_motion_rad_s * 60.0

    Args:
        altitude_km: Representative circular design altitude in kilometres.
        earth_radius_km: Equatorial Earth radius in kilometres from SGP4 constants.
        mu_km3_s2: Earth gravitational parameter in km^3/s^2 from SGP4 constants.

    Returns:
        Kozai mean motion in radians per minute.

    Raises:
        ValueError: If altitude_km or semi_major_axis_km is not physically positive.
    """
    if altitude_km <= 0.0:
        raise ValueError(f"altitude_km must be positive, got {altitude_km}")
    semi_major_axis_km = earth_radius_km + altitude_km
    if semi_major_axis_km <= 0.0:
        raise ValueError(
            f"semi_major_axis_km must be positive, got {semi_major_axis_km}"
        )

    mean_motion_rad_s = math.sqrt(mu_km3_s2 / (semi_major_axis_km**3))
    return mean_motion_rad_s * 60.0


def datetime_to_sgp4_epoch(epoch_utc: datetime) -> tuple[float, float, float]:
    """Derive SGP4 epoch representation from a timezone-aware UTC datetime.

    SGP4 represents the epoch internally as days elapsed since 1949-12-31 00:00:00 UTC.
    The Julian Date of 1949-12-31 00:00:00 UTC is exactly 2433281.5.
    Therefore:
        epoch_days = (jd + fr) - 2433281.5

    Args:
        epoch_utc: Timezone-aware datetime explicitly in UTC.

    Returns:
        Tuple of (epoch_days, jd, fr) where:
            epoch_days: Float days since 1949-12-31 00:00:00 UTC for Satrec.sgp4init.
            jd: Whole-day Julian Date component from sgp4.api.jday.
            fr: Fractional-day Julian Date component from sgp4.api.jday.

    Raises:
        ValueError: If epoch_utc is naive or has a non-UTC offset.
    """
    if epoch_utc.tzinfo is None:
        raise ValueError("epoch_utc must be timezone-aware.")
    offset = epoch_utc.utcoffset()
    if offset is None or offset != timedelta(0):
        raise ValueError(
            f"epoch_utc must have UTC timezone (+00:00 or Z), got offset {offset}."
        )

    jd, fr = jday(
        epoch_utc.year,
        epoch_utc.month,
        epoch_utc.day,
        epoch_utc.hour,
        epoch_utc.minute,
        epoch_utc.second + epoch_utc.microsecond * 1e-6,
    )
    # Julian date for 1949-12-31 00:00:00 UTC is 2433281.5
    epoch_days = (jd + fr) - 2433281.5
    return epoch_days, jd, fr


def create_sgp4_satellite(
    satellite: SatelliteConfig,
    epoch_utc: datetime,
    satnum: int = 1,
    gravity_model: str = "WGS72",
) -> Sgp4SatelliteRecord:
    """Construct an initialized Sgp4SatelliteRecord from a SatelliteConfig.

    Args:
        satellite: Validated SatelliteConfig.
        epoch_utc: Timezone-aware UTC epoch datetime for the orbital elements.
        satnum: Positive integer satellite catalog number (defaults to 1).
        gravity_model: Gravity model name, must be 'WGS72' (default) or 'WGS84'.

    Returns:
        Sgp4SatelliteRecord containing the initialized Satrec and associated metadata.

    Raises:
        ValueError: If satnum is not a positive integer, gravity_model is unsupported,
                    epoch_utc is not UTC, or SGP4 initialization produces an error code.
    """
    if isinstance(satnum, bool) or not isinstance(satnum, int) or satnum <= 0:
        raise ValueError(f"satnum must be a positive integer, got {satnum!r}")

    if gravity_model not in GRAVITY_MODELS:
        supported = list(GRAVITY_MODELS.keys())
        raise ValueError(
            f"Unsupported gravity_model '{gravity_model}'. Supported models: {supported}"
        )

    whichconst, grav_consts = GRAVITY_MODELS[gravity_model]

    # Validate epoch and compute SGP4 epoch days
    epoch_days, _, _ = datetime_to_sgp4_epoch(epoch_utc)

    # Convert design altitude to Kozai mean motion using the model's constants
    no_kozai_rad_min = design_altitude_to_mean_motion(
        altitude_km=satellite.altitude_km,
        earth_radius_km=grav_consts.radiusearthkm,
        mu_km3_s2=grav_consts.mu,
    )

    # Instantiate Satrec and initialize using C++ accelerated sgp4init.
    # Note: Compiled C extension method sgp4init only accepts positional arguments.
    satrec = Satrec()
    satrec.sgp4init(
        whichconst,
        "i",  # Improved operational mode
        satnum,
        epoch_days,
        satellite.bstar,
        0.0,  # ndot
        0.0,  # nddot
        satellite.eccentricity,
        math.radians(satellite.arg_perigee_deg),
        math.radians(satellite.inclination_deg),
        math.radians(satellite.mean_anomaly_deg),
        no_kozai_rad_min,
        math.radians(satellite.raan_deg),
    )

    if satrec.error != 0:
        raise ValueError(
            f"Satrec.sgp4init failed with error code {satrec.error} for satellite '{satellite.satellite_id}'."
        )

    return Sgp4SatelliteRecord(
        satellite_id=satellite.satellite_id,
        satnum=satnum,
        satrec=satrec,
        epoch_utc=epoch_utc,
        gravity_model=gravity_model,
    )
