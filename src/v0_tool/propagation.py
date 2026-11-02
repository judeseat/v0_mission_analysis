"""Time-grid generation and single-satellite analytical SGP4 propagation.

This module provides:
  - Inclusive time-grid generation based on AnalysisConfig.
  - Split Julian-date conversion (jd, fr) for python-sgp4.
  - Single-satellite analytical propagation using Satrec.sgp4_array.
  - The library-independent EphemerisProduct container.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import math

import numpy as np
import sgp4.api
from sgp4.api import SGP4_ERRORS, jday

from v0_tool.config import AnalysisConfig
from v0_tool.sgp4_adapter import Sgp4SatelliteRecord


class Sgp4PropagationError(RuntimeError):
    """Raised when SGP4 analytical propagation reports one or more non-zero error codes."""

    pass


@dataclass(frozen=True)
class EphemerisProduct:
    """Library-independent ephemeris result for a single satellite.

    Contains time-tagged position and velocity states in the True Equator,
    Mean Equinox (TEME) inertial frame as output by analytical SGP4 propagation.

    Note on immutability:
        While this dataclass wrapper is frozen, the contained NumPy arrays
        are standard mutable buffer objects and are not deeply immutable.
    """

    satellite_id: str
    timestamps_utc: np.ndarray  # shape (N,), dtype=object (datetime)
    position_teme_km: np.ndarray  # shape (N, 3), dtype=np.float64
    velocity_teme_km_s: np.ndarray  # shape (N, 3), dtype=np.float64
    sgp4_error_codes: np.ndarray  # shape (N,), integer dtype
    frame: str = "TEME"
    position_unit: str = "km"
    velocity_unit: str = "km/s"
    propagation_model: str = "SGP4"
    gravity_model: str = "WGS72"


def generate_time_grid(analysis: AnalysisConfig) -> np.ndarray:
    """Generate an inclusive uniform 1D array of UTC datetimes spanning [start_time_utc, end_time_utc].

    Steps are generated using integer indexing offsets (k * interval) rather than repeated
    floating-point addition, and the final sample is explicitly pegged to end_time_utc.

    Args:
        analysis: Validated AnalysisConfig.

    Returns:
        1D NumPy array of UTC datetime objects with shape (N,), dtype=object.

    Raises:
        ValueError: If total analysis duration is not an integer multiple of
                    ephemeris_interval_seconds within a 1-microsecond tolerance.
    """
    duration_s = analysis.duration_seconds
    interval_s = analysis.ephemeris_interval_seconds

    steps_float = duration_s / interval_s
    steps_int = round(steps_float)

    # Microsecond tolerance check (1e-6 seconds)
    discrepancy = abs(duration_s - (steps_int * interval_s))
    if discrepancy > 1e-6:
        raise ValueError(
            f"Analysis duration ({duration_s} s) must be an integer multiple of "
            f"ephemeris_interval_seconds ({interval_s} s). Remainder: {discrepancy:.6f} s."
        )

    # Generate samples from integer step indices
    timestamps = [
        analysis.start_time_utc + timedelta(seconds=k * interval_s)
        for k in range(steps_int)
    ]
    # Peg final sample strictly to end_time_utc
    timestamps.append(analysis.end_time_utc)

    return np.array(timestamps, dtype=object)


def datetimes_to_split_jd(timestamps: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Convert a 1D array of UTC datetimes into split (jd, fr) float64 Julian date arrays.

    Preserves separate whole-day (jd) and fractional-day (fr) components to avoid
    floating-point precision loss in SGP4 coordinate evaluation.

    Args:
        timestamps: 1D array of timezone-aware UTC datetime objects.

    Returns:
        Tuple of (jd, fr) where each is a 1D NumPy array of dtype float64 with shape (N,).
    """
    n_samples = len(timestamps)
    jd_arr = np.empty(n_samples, dtype=np.float64)
    fr_arr = np.empty(n_samples, dtype=np.float64)

    for i, dt in enumerate(timestamps):
        sec = dt.second + dt.microsecond * 1e-6
        jd, fr = jday(dt.year, dt.month, dt.day, dt.hour, dt.minute, sec)
        jd_arr[i] = jd
        fr_arr[i] = fr

    return jd_arr, fr_arr


def _validate_timestamps(timestamps: np.ndarray) -> None:
    """Validate timestamp array contract before propagation."""
    if not isinstance(timestamps, np.ndarray):
        raise ValueError(f"timestamps must be a NumPy array, got {type(timestamps)}")
    if timestamps.ndim != 1:
        raise ValueError(f"timestamps must be 1-dimensional, got shape {timestamps.shape}")
    if len(timestamps) == 0:
        raise ValueError("timestamps array must not be empty")

    prev_dt = None
    for i, item in enumerate(timestamps):
        if not isinstance(item, datetime):
            raise ValueError(f"timestamp at index {i} is not a datetime: {type(item)}")
        if item.tzinfo is None:
            raise ValueError(f"timestamp at index {i} must be timezone-aware")
        offset = item.utcoffset()
        if offset is None or offset != timedelta(0):
            raise ValueError(f"timestamp at index {i} must have UTC offset (+00:00 or Z), got {offset}")

        if prev_dt is not None:
            if item <= prev_dt:
                raise ValueError(
                    f"timestamps must be strictly increasing with no duplicates. "
                    f"Failed at index {i}: current {item} <= previous {prev_dt}"
                )
        prev_dt = item


def _check_sgp4_errors(
    satellite_id: str,
    timestamps: np.ndarray,
    error_codes: np.ndarray,
) -> None:
    """Inspect SGP4 error code array and raise Sgp4PropagationError if any are non-zero."""
    failing_indices = np.nonzero(error_codes)[0]
    if len(failing_indices) == 0:
        return

    first_idx = int(failing_indices[0])
    first_time = timestamps[first_idx]
    unique_codes = sorted(set(error_codes[failing_indices].tolist()))

    error_descriptions = []
    for code in unique_codes:
        desc = SGP4_ERRORS.get(code, "Unknown SGP4 error code")
        error_descriptions.append(f"Code {code}: {desc}")

    details = "; ".join(error_descriptions)
    raise Sgp4PropagationError(
        f"SGP4 propagation failed for satellite '{satellite_id}'. "
        f"First failure at index {first_idx} (time: {first_time}). "
        f"Encountered error codes: [{details}]."
    )


def propagate_satellite(
    record: Sgp4SatelliteRecord,
    timestamps: np.ndarray,
) -> EphemerisProduct:
    """Propagate a single SGP4 satellite across the provided time grid.

    Args:
        record: Sgp4SatelliteRecord containing the initialized Satrec and metadata.
        timestamps: 1D NumPy array of strictly increasing UTC datetimes.

    Returns:
        EphemerisProduct containing time-tagged TEME position and velocity vectors.

    Raises:
        ValueError: If timestamps fail validation.
        Sgp4PropagationError: If any propagation sample reports a non-zero SGP4 error code.
    """
    _validate_timestamps(timestamps)

    jd_arr, fr_arr = datetimes_to_split_jd(timestamps)

    # Call accelerated Satrec.sgp4_array on split Julian dates
    error_codes, positions, velocities = record.satrec.sgp4_array(jd_arr, fr_arr)

    # Validate error codes and fail fast if any non-zero code exists
    _check_sgp4_errors(record.satellite_id, timestamps, error_codes)

    return EphemerisProduct(
        satellite_id=record.satellite_id,
        timestamps_utc=timestamps,
        position_teme_km=positions,
        velocity_teme_km_s=velocities,
        sgp4_error_codes=error_codes,
        frame="TEME",
        position_unit="km",
        velocity_unit="km/s",
        propagation_model="SGP4",
        gravity_model=record.gravity_model,
    )
