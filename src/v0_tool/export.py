"""Export and run-manifest generation for the Stage 1 smoke workflow.

This module persists an existing in-memory SmokeRunResult and validated
ScenarioConfig to disk into a run-specific directory without altering or
rerunning any scientific calculation.

Products generated:
  - validated_scenario.json: Serialized validated ScenarioConfig.
  - ephemeris.csv: Fixed-schema time-series ephemeris in TEME (km, km/s).
  - access_windows.csv: Discrete geometric ground-access windows.
  - run_manifest.json: Full execution provenance, environment, and assumptions.

Export uses a temporary sibling directory and an atomic rename to guarantee
that partial/corrupted files are never left on disk if an error occurs.
"""

import csv
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from typing import Any
import uuid

import numpy as np
import sgp4.api

from v0_tool.config import ScenarioConfig
from v0_tool.workflow import SmokeRunResult

# Expected regular files in the run directory
EXPECTED_PRODUCT_FILES = {
    "validated_scenario.json",
    "ephemeris.csv",
    "access_windows.csv",
    "run_manifest.json",
}

# Conservative pattern: alphanumeric, hyphen, underscore
SAFE_RUN_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]+$")

# Dependencies to inventory in the run manifest
TRACKED_DEPENDENCIES = [
    "numpy",
    "sgp4",
    "skyfield",
    "pydantic",
    "pyyaml",
    "matplotlib",
]

# Standard modelling assumptions recorded in the manifest
STANDARD_MODELLING_ASSUMPTIONS = [
    "synthetic representative design orbit",
    "analytical SGP4 propagation",
    "WGS72 propagation constants",
    "zero B-star",
    "TEME state output",
    "geometric minimum-elevation access only",
    "Skyfield built-in time tables",
    "no communications, scheduling or operational constraints",
]


@dataclass(frozen=True)
class ExportResult:
    """Resolved paths to exported artifacts and output directory."""

    output_directory: Path
    validated_scenario_path: Path
    ephemeris_path: Path
    access_windows_path: Path
    run_manifest_path: Path


def format_utc_iso(dt: datetime) -> str:
    """Format a timezone-aware UTC datetime with explicit Z and microsecond preservation.

    Example: 2026-10-26T00:00:00Z or 2026-10-26T01:31:17.023656Z
    """
    if dt.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware.")
    offset = dt.utcoffset()
    if offset is None or offset != timedelta(0):
        raise ValueError(f"Datetime must have UTC timezone (+00:00 or Z), got {offset}")

    dt_utc = dt.astimezone(timezone.utc)
    if dt_utc.microsecond != 0:
        return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_float(val: float | None) -> str:
    """Format floating point numbers preserving high scientific precision (.15g)."""
    if val is None:
        return ""
    return format(val, ".15g")


def _validate_run_id_safe(run_id: str) -> None:
    """Validate that run_id contains only safe characters and no path separators."""
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id must be a non-empty string.")
    if run_id != run_id.strip():
        raise ValueError("run_id must not contain leading or trailing whitespace.")
    if not SAFE_RUN_ID_REGEX.match(run_id):
        raise ValueError(
            f"run_id '{run_id}' contains unsafe characters. "
            "Must contain only letters, digits, underscores, and hyphens."
        )


def _validate_consistency(scenario: ScenarioConfig, result: SmokeRunResult) -> None:
    """Validate scenario and result data contracts in memory before touching disk."""
    if result.scenario_id != scenario.scenario_id:
        raise ValueError(
            f"Scenario ID mismatch: result '{result.scenario_id}' != scenario '{scenario.scenario_id}'"
        )

    if len(scenario.satellites) != 1:
        raise ValueError(f"Expected exactly 1 satellite in scenario, got {len(scenario.satellites)}")
    if len(scenario.ground_stations) != 1:
        raise ValueError(f"Expected exactly 1 ground station in scenario, got {len(scenario.ground_stations)}")

    sat_id = scenario.satellites[0].satellite_id
    station_id = scenario.ground_stations[0].station_id

    if result.satellite_id != sat_id:
        raise ValueError(f"Satellite ID mismatch: result '{result.satellite_id}' != scenario '{sat_id}'")
    if result.ground_station_id != station_id:
        raise ValueError(f"Station ID mismatch: result '{result.ground_station_id}' != scenario '{station_id}'")

    if result.analysis_start_utc != scenario.analysis.start_time_utc:
        raise ValueError("Analysis start time mismatch between scenario and result.")
    if result.analysis_end_utc != scenario.analysis.end_time_utc:
        raise ValueError("Analysis end time mismatch between scenario and result.")

    # Ephemeris contracts
    eph = result.ephemeris
    if eph.satellite_id != sat_id:
        raise ValueError(f"Ephemeris satellite ID mismatch: '{eph.satellite_id}' != '{sat_id}'")

    n_samples = len(eph.timestamps_utc)
    if eph.timestamps_utc.ndim != 1:
        raise ValueError("Ephemeris timestamps array must be 1-dimensional.")
    if eph.position_teme_km.shape != (n_samples, 3):
        raise ValueError(f"Ephemeris positions shape must be ({n_samples}, 3), got {eph.position_teme_km.shape}")
    if eph.velocity_teme_km_s.shape != (n_samples, 3):
        raise ValueError(f"Ephemeris velocities shape must be ({n_samples}, 3), got {eph.velocity_teme_km_s.shape}")
    if eph.sgp4_error_codes.shape != (n_samples,):
        raise ValueError(f"Ephemeris error codes shape must be ({n_samples},), got {eph.sgp4_error_codes.shape}")
    if not np.issubdtype(eph.sgp4_error_codes.dtype, np.integer):
        raise ValueError("Ephemeris error codes must have integer dtype.")

    if not np.all(np.isfinite(eph.position_teme_km)):
        raise ValueError("Ephemeris position array contains non-finite values (NaN or Inf).")
    if not np.all(np.isfinite(eph.velocity_teme_km_s)):
        raise ValueError("Ephemeris velocity array contains non-finite values (NaN or Inf).")

    for dt in eph.timestamps_utc:
        if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
            raise ValueError("All ephemeris timestamps must be timezone-aware UTC.")

    # Access window contracts
    for w in result.access_windows:
        if w.satellite_id != sat_id:
            raise ValueError(f"AccessWindow satellite_id '{w.satellite_id}' != '{sat_id}'")
        if w.ground_station_id != station_id:
            raise ValueError(f"AccessWindow ground_station_id '{w.ground_station_id}' != '{station_id}'")
        if not (scenario.analysis.start_time_utc <= w.start_time_utc < w.end_time_utc <= scenario.analysis.end_time_utc):
            raise ValueError(f"AccessWindow [{w.start_time_utc}, {w.end_time_utc}] out of scenario bounds.")


def _get_git_metadata() -> tuple[str | None, bool | None]:
    """Retrieve Git commit hash and dirty status safely using bounded subprocesses."""
    git_commit: str | None = None
    git_dirty: bool | None = None

    try:
        proc_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2.0,
            shell=False,
        )
        if proc_hash.returncode == 0:
            commit = proc_hash.stdout.strip()
            if commit:
                git_commit = commit

        proc_status = subprocess.run(
            ["git", "status", "--porcelain"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2.0,
            shell=False,
        )
        if proc_status.returncode == 0:
            git_dirty = bool(proc_status.stdout.strip())
    except Exception:
        # Failure to run Git must never fail export
        pass

    return git_commit, git_dirty


def _get_dependencies_metadata() -> dict[str, str | None]:
    """Retrieve installed versions of tracked dependencies."""
    deps: dict[str, str | None] = {}
    for pkg in TRACKED_DEPENDENCIES:
        try:
            deps[pkg] = importlib.metadata.version(pkg)
        except Exception:
            deps[pkg] = None
    return deps


def _write_validated_scenario(target_file: Path, scenario: ScenarioConfig) -> None:
    """Serialize the validated ScenarioConfig to formatted JSON."""
    raw_dict = json.loads(scenario.model_dump_json())
    with open(target_file, "w", encoding="utf-8") as f:
        json.dump(raw_dict, f, indent=2)
        f.write("\n")


def _write_ephemeris_csv(target_file: Path, result: SmokeRunResult) -> None:
    """Write ephemeris time-series to CSV."""
    eph = result.ephemeris
    fieldnames = [
        "satellite_id",
        "timestamp_utc",
        "position_teme_x_km",
        "position_teme_y_km",
        "position_teme_z_km",
        "velocity_teme_x_km_s",
        "velocity_teme_y_km_s",
        "velocity_teme_z_km_s",
        "sgp4_error_code",
    ]

    with open(target_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(fieldnames)

        sat_id = eph.satellite_id
        for i, dt in enumerate(eph.timestamps_utc):
            writer.writerow(
                [
                    sat_id,
                    format_utc_iso(dt),
                    _format_float(float(eph.position_teme_km[i, 0])),
                    _format_float(float(eph.position_teme_km[i, 1])),
                    _format_float(float(eph.position_teme_km[i, 2])),
                    _format_float(float(eph.velocity_teme_km_s[i, 0])),
                    _format_float(float(eph.velocity_teme_km_s[i, 1])),
                    _format_float(float(eph.velocity_teme_km_s[i, 2])),
                    int(eph.sgp4_error_codes[i]),
                ]
            )


def _write_access_windows_csv(target_file: Path, result: SmokeRunResult) -> None:
    """Write discrete ground-access windows to CSV (header-only if empty)."""
    fieldnames = [
        "satellite_id",
        "ground_station_id",
        "start_time_utc",
        "end_time_utc",
        "duration_seconds",
        "minimum_elevation_deg",
        "culmination_time_utc",
        "maximum_elevation_deg",
        "access_type",
        "geometry_method",
    ]

    with open(target_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(fieldnames)

        for w in result.access_windows:
            culm_str = format_utc_iso(w.culmination_time_utc) if w.culmination_time_utc is not None else ""
            max_el_str = _format_float(w.maximum_elevation_deg) if w.maximum_elevation_deg is not None else ""

            writer.writerow(
                [
                    w.satellite_id,
                    w.ground_station_id,
                    format_utc_iso(w.start_time_utc),
                    format_utc_iso(w.end_time_utc),
                    _format_float(w.duration_seconds),
                    _format_float(w.minimum_elevation_deg),
                    culm_str,
                    max_el_str,
                    w.access_type,
                    w.geometry_method,
                ]
            )


def _write_run_manifest(target_file: Path, scenario: ScenarioConfig, result: SmokeRunResult) -> None:
    """Write comprehensive run manifest JSON."""
    git_commit, git_dirty = _get_git_metadata()
    deps = _get_dependencies_metadata()

    # Determine SGP4 compiled acceleration status
    sgp4_accel = getattr(sgp4.api, "accelerated", False)

    eph = result.ephemeris
    non_zero_errors = int(np.count_nonzero(eph.sgp4_error_codes))

    manifest_dict: dict[str, Any] = {
        "schema_version": "1.0",
        "scenario_id": result.scenario_id,
        "run_id": result.run_id,
        "analysis": {
            "start_time_utc": format_utc_iso(result.analysis_start_utc),
            "end_time_utc": format_utc_iso(result.analysis_end_utc),
            "satellite_id": result.satellite_id,
            "ground_station_id": result.ground_station_id,
            "propagation_model": eph.propagation_model,
            "gravity_model": eph.gravity_model,
            "frame": eph.frame,
            "position_unit": eph.position_unit,
            "velocity_unit": eph.velocity_unit,
            "ephemeris_samples_count": len(eph.timestamps_utc),
            "access_windows_count": len(result.access_windows),
            "sgp4_non_zero_errors_count": non_zero_errors,
        },
        "runtime": {
            "completed_at_utc": format_utc_iso(result.completed_at_utc),
            "execution_duration_seconds": result.execution_duration_seconds,
            "python_version": sys.version,
            "platform": platform.platform(),
            "v0_tool_version": "0.1.0",
            "dependencies": deps,
            "sgp4_acceleration_active": bool(sgp4_accel),
            "git_commit": git_commit,
            "git_dirty": git_dirty,
        },
        "products": {
            "validated_scenario": "validated_scenario.json",
            "ephemeris": "ephemeris.csv",
            "access_windows": "access_windows.csv",
            "manifest": "run_manifest.json",
        },
        "modelling_assumptions": STANDARD_MODELLING_ASSUMPTIONS,
    }

    with open(target_file, "w", encoding="utf-8") as f:
        json.dump(manifest_dict, f, indent=2)
        f.write("\n")


def export_smoke_run(
    scenario: ScenarioConfig,
    result: SmokeRunResult,
    *,
    base_output_dir: Path | str | None = None,
) -> ExportResult:
    """Persist a completed SmokeRunResult and validated ScenarioConfig to disk.

    Args:
        scenario: Validated ScenarioConfig.
        result: Completed SmokeRunResult.
        base_output_dir: Optional base directory under which the run directory is created.
            If None, uses scenario.output.output_dir (interpreted relative to current
            working directory if relative).

    Returns:
        ExportResult containing resolved paths to the output directory and all four files.

    Raises:
        ValueError: If run_id is unsafe or if scenario/result validation fails.
        FileExistsError: If the final run directory already exists.
        OSError: If an unrecoverable disk error occurs.
    """
    # 1. Validate run_id against conservative safe pattern
    _validate_run_id_safe(result.run_id)

    # 2. Perform all scenario/result consistency validation BEFORE disk operations
    _validate_consistency(scenario, result)

    # 3. Resolve destination paths
    if base_output_dir is None:
        base_dir = scenario.output.output_dir.resolve()
    else:
        base_dir = Path(base_output_dir).resolve()

    final_run_dir = (base_dir / result.run_id).resolve()

    # Reject if final run directory already exists (no overwrite policy)
    if final_run_dir.exists():
        raise FileExistsError(f"Target run directory already exists: {final_run_dir}")

    # 4. Prepare temporary staging sibling directory under base_dir
    base_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = base_dir / f".tmp_{result.run_id}_{uuid.uuid4().hex[:8]}"
    tmp_dir.mkdir(parents=False, exist_ok=False)

    try:
        # 5. Write all products into temporary staging directory
        scenario_file = tmp_dir / "validated_scenario.json"
        ephemeris_file = tmp_dir / "ephemeris.csv"
        access_file = tmp_dir / "access_windows.csv"
        manifest_file = tmp_dir / "run_manifest.json"

        _write_validated_scenario(scenario_file, scenario)
        _write_ephemeris_csv(ephemeris_file, result)
        _write_access_windows_csv(access_file, result)
        _write_run_manifest(manifest_file, scenario, result)

        # 6. Verify that temporary directory contains exactly the four expected files
        staged_files = {p.name for p in tmp_dir.iterdir() if p.is_file()}
        if staged_files != EXPECTED_PRODUCT_FILES:
            raise RuntimeError(
                f"Staging verification failed: expected {EXPECTED_PRODUCT_FILES}, got {staged_files}"
            )

        # Re-check that final run directory does not exist before rename
        if final_run_dir.exists():
            raise FileExistsError(f"Target run directory appeared before rename: {final_run_dir}")

        # 7. Atomic rename: promote temporary directory to final run directory
        tmp_dir.rename(final_run_dir)

    except Exception:
        # Failure cleanup: remove temporary staging directory and re-raise
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    # 8. Return ExportResult referencing paths in final run directory
    return ExportResult(
        output_directory=final_run_dir,
        validated_scenario_path=final_run_dir / "validated_scenario.json",
        ephemeris_path=final_run_dir / "ephemeris.csv",
        access_windows_path=final_run_dir / "access_windows.csv",
        run_manifest_path=final_run_dir / "run_manifest.json",
    )
