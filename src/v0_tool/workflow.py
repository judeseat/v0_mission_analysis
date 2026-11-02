"""Controlled workflow orchestrator for the Stage 1 mission-analysis smoke test.

Orchestrates the in-memory execution sequence:
    scenario ingestion
    -> scope validation (single satellite, single ground station)
    -> SGP4 satellite construction
    -> time-grid generation
    -> analytical SGP4 propagation
    -> geometric ground-access calculation
    -> consolidated library-independent result (SmokeRunResult)

This module composes existing scientific functions and does not reproduce
their calculations or perform file/disk side effects.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import time
import uuid

from v0_tool.access import AccessWindow, calculate_access_windows
from v0_tool.config import ScenarioConfig, load_scenario
from v0_tool.propagation import EphemerisProduct, generate_time_grid, propagate_satellite
from v0_tool.sgp4_adapter import create_sgp4_satellite


class SmokeWorkflowConfigurationError(ValueError):
    """Raised when a scenario is valid generally but incompatible with the Stage 1 smoke workflow."""

    pass


@dataclass(frozen=True)
class SmokeRunResult:
    """Consolidated library-independent result of the Stage 1 smoke workflow."""

    scenario_id: str
    run_id: str
    analysis_start_utc: datetime
    analysis_end_utc: datetime
    satellite_id: str
    ground_station_id: str
    ephemeris: EphemerisProduct
    access_windows: tuple[AccessWindow, ...]
    execution_duration_seconds: float
    completed_at_utc: datetime


def generate_run_id(scenario_id: str) -> str:
    """Generate a unique run identifier using full uuid4 hex.

    Format: <scenario_id>_<full uuid4 hex>
    Example: smoke_01_a1b2c3d4e5f64715a9b0123456789abc
    """
    return f"{scenario_id}_{uuid.uuid4().hex}"


def run_smoke_workflow(
    scenario: ScenarioConfig | Path | str,
    *,
    run_id: str | None = None,
) -> SmokeRunResult:
    """Execute the Stage 1 in-memory mission-analysis smoke workflow.

    Args:
        scenario: Validated ScenarioConfig or path to YAML scenario file.
        run_id: Optional explicit run identifier. If provided, must not be empty,
            whitespace-only, or contain leading/trailing whitespace.

    Returns:
        SmokeRunResult: Consolidated library-independent execution result.

    Raises:
        ValueError: If explicit run_id is invalid.
        SmokeWorkflowConfigurationError: If scenario does not contain exactly one
            satellite and one ground station.
    """
    # Start monotonic timer immediately before the first workflow action
    start_monotonic = time.perf_counter()

    # 1. Validate or generate run_id
    if run_id is not None:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("Explicit run_id must not be empty or whitespace-only.")
        if run_id != run_id.strip():
            raise ValueError("Explicit run_id must not contain leading or trailing whitespace.")

    # 2. Ingest scenario
    if isinstance(scenario, (Path, str)):
        scenario_config = load_scenario(scenario)
    elif isinstance(scenario, ScenarioConfig):
        scenario_config = scenario
    else:
        raise TypeError(
            f"Expected ScenarioConfig, Path, or str; got {type(scenario).__name__}"
        )

    # 3. Enforce Stage 1 single-asset scope
    n_sats = len(scenario_config.satellites)
    if n_sats != 1:
        raise SmokeWorkflowConfigurationError(
            f"Stage 1 smoke workflow requires exactly 1 satellite; received {n_sats}."
        )

    n_stations = len(scenario_config.ground_stations)
    if n_stations != 1:
        raise SmokeWorkflowConfigurationError(
            f"Stage 1 smoke workflow requires exactly 1 ground station; received {n_stations}."
        )

    active_run_id = run_id if run_id is not None else generate_run_id(scenario_config.scenario_id)

    satellite_cfg = scenario_config.satellites[0]
    station_cfg = scenario_config.ground_stations[0]
    analysis_cfg = scenario_config.analysis

    # 4. Construct SGP4 satellite record
    sat_record = create_sgp4_satellite(
        satellite=satellite_cfg,
        epoch_utc=analysis_cfg.start_time_utc,
    )

    # 5. Generate time grid
    time_grid = generate_time_grid(analysis_cfg)

    # 6. Propagate satellite
    ephemeris = propagate_satellite(sat_record, time_grid)

    # 7. Calculate geometric access windows
    access_windows = calculate_access_windows(
        satellite_record=sat_record,
        ground_station=station_cfg,
        start_time_utc=analysis_cfg.start_time_utc,
        end_time_utc=analysis_cfg.end_time_utc,
    )

    # Measure execution duration and completion time
    execution_duration = time.perf_counter() - start_monotonic
    completed_at = datetime.now(timezone.utc)

    # 8. Return consolidated result
    return SmokeRunResult(
        scenario_id=scenario_config.scenario_id,
        run_id=active_run_id,
        analysis_start_utc=analysis_cfg.start_time_utc,
        analysis_end_utc=analysis_cfg.end_time_utc,
        satellite_id=satellite_cfg.satellite_id,
        ground_station_id=station_cfg.station_id,
        ephemeris=ephemeris,
        access_windows=access_windows,
        execution_duration_seconds=execution_duration,
        completed_at_utc=completed_at,
    )
