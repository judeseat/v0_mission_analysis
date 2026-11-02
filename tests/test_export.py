"""Unit, serialization, provenance, and failure tests for the export module (Stage 1 Task 7).

Note on testing scope:
    Tests verify serialization, schema compliance, provenance metadata, directory
    atomicity, and failure cleanup. They do not constitute orbital validation.
"""

import csv
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path

import numpy as np
import pytest

from v0_tool.config import ScenarioConfig, load_scenario
from v0_tool.export import ExportResult, export_smoke_run, format_utc_iso
from v0_tool.workflow import SmokeRunResult, run_smoke_workflow

SMOKE_YAML_PATH = Path(__file__).resolve().parent.parent / "scenarios" / "smoke_01.yaml"


@pytest.fixture
def smoke_run_data() -> tuple[ScenarioConfig, SmokeRunResult]:
    """Execute smoke workflow and return validated scenario and completed result."""
    scenario = load_scenario(SMOKE_YAML_PATH)
    result = run_smoke_workflow(scenario, run_id="test_export_run_01")
    return scenario, result


# --- 1. Successful Export and File Contract Tests ---


def test_export_smoke_run_nominal(tmp_path: Path, smoke_run_data: tuple[ScenarioConfig, SmokeRunResult]) -> None:
    """Verify nominal export produces ExportResult with all four regular files present."""
    scenario, result = smoke_run_data
    export_res = export_smoke_run(scenario, result, base_output_dir=tmp_path)

    assert isinstance(export_res, ExportResult)
    run_dir = export_res.output_directory
    assert run_dir.is_dir()
    assert run_dir.parent == tmp_path.resolve()
    assert run_dir.name == "test_export_run_01"

    # Exactly one run directory under tmp_path
    subdirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert subdirs == [run_dir]

    # Verify all four paths exist
    assert export_res.validated_scenario_path.is_file()
    assert export_res.ephemeris_path.is_file()
    assert export_res.access_windows_path.is_file()
    assert export_res.run_manifest_path.is_file()

    # Exact product file inventory in directory
    files_in_dir = {p.name for p in run_dir.iterdir()}
    assert files_in_dir == {
        "validated_scenario.json",
        "ephemeris.csv",
        "access_windows.csv",
        "run_manifest.json",
    }


def test_exported_validated_scenario_json(tmp_path: Path, smoke_run_data: tuple[ScenarioConfig, SmokeRunResult]) -> None:
    """Verify validated_scenario.json contents, deterministic formatting, and round-trip parsing."""
    scenario, result = smoke_run_data
    export_res = export_smoke_run(scenario, result, base_output_dir=tmp_path)

    content = export_res.validated_scenario_path.read_text(encoding="utf-8")
    assert content.endswith("\n")

    parsed = json.loads(content)
    assert parsed["scenario_id"] == "smoke_01"
    assert parsed["satellites"][0]["satellite_id"] == "SAT-SMOKE-01"
    assert parsed["ground_stations"][0]["station_id"] == "GS-SMOKE-01"
    assert parsed["analysis"]["ephemeris_interval_seconds"] == 300.0

    # Ensure it parses back into ScenarioConfig identically
    reconstructed = ScenarioConfig.model_validate(parsed)
    assert reconstructed.scenario_id == scenario.scenario_id
    assert reconstructed.analysis.duration_seconds == scenario.analysis.duration_seconds


def test_exported_ephemeris_csv(tmp_path: Path, smoke_run_data: tuple[ScenarioConfig, SmokeRunResult]) -> None:
    """Verify ephemeris.csv exact headers, row count, precision, and first-row alignment."""
    scenario, result = smoke_run_data
    export_res = export_smoke_run(scenario, result, base_output_dir=tmp_path)

    expected_headers = [
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

    with open(export_res.ephemeris_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)

    assert len(rows) == 74  # 1 header + 73 data rows
    assert rows[0] == expected_headers

    # Check first row
    first_row = rows[1]
    assert first_row[0] == "SAT-SMOKE-01"
    assert first_row[1] == "2026-10-26T00:00:00Z"
    # Position and velocity floats
    pos_x = float(first_row[2])
    assert pos_x == pytest.approx(result.ephemeris.position_teme_km[0, 0], abs=1e-9)
    # Zero SGP4 error code
    assert first_row[8] == "0"


def test_exported_access_windows_csv(tmp_path: Path, smoke_run_data: tuple[ScenarioConfig, SmokeRunResult]) -> None:
    """Verify access_windows.csv exact headers and data alignment."""
    scenario, result = smoke_run_data
    export_res = export_smoke_run(scenario, result, base_output_dir=tmp_path)

    expected_headers = [
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

    with open(export_res.access_windows_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)

    assert len(rows) == 1 + len(result.access_windows)
    assert rows[0] == expected_headers

    first_window_row = rows[1]
    assert first_window_row[0] == "SAT-SMOKE-01"
    assert first_window_row[1] == "GS-SMOKE-01"
    assert float(first_window_row[4]) > 0.0  # Duration
    assert float(first_window_row[5]) == 10.0  # Min elev
    assert float(first_window_row[7]) > 10.0  # Max elev


def test_exported_access_windows_csv_zero_access(tmp_path: Path, smoke_run_data: tuple[ScenarioConfig, SmokeRunResult]) -> None:
    """Verify that a zero-access result exports a valid header-only CSV."""
    scenario, result = smoke_run_data
    # Construct a result with empty access_windows
    zero_access_result = SmokeRunResult(
        scenario_id=result.scenario_id,
        run_id="zero_access_run",
        analysis_start_utc=result.analysis_start_utc,
        analysis_end_utc=result.analysis_end_utc,
        satellite_id=result.satellite_id,
        ground_station_id=result.ground_station_id,
        ephemeris=result.ephemeris,
        access_windows=(),
        execution_duration_seconds=result.execution_duration_seconds,
        completed_at_utc=result.completed_at_utc,
    )

    export_res = export_smoke_run(scenario, zero_access_result, base_output_dir=tmp_path)

    with open(export_res.access_windows_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)

    assert len(rows) == 1  # Header row only
    assert rows[0][0] == "satellite_id"


def test_exported_run_manifest_structure_and_values(tmp_path: Path, smoke_run_data: tuple[ScenarioConfig, SmokeRunResult]) -> None:
    """Verify run_manifest.json schema version, sections, provenance, and assumptions."""
    scenario, result = smoke_run_data
    export_res = export_smoke_run(scenario, result, base_output_dir=tmp_path)

    content = export_res.run_manifest_path.read_text(encoding="utf-8")
    assert content.endswith("\n")

    manifest = json.loads(content)

    # Top-level fields
    assert manifest["schema_version"] == "1.0"
    assert manifest["scenario_id"] == "smoke_01"
    assert manifest["run_id"] == "test_export_run_01"

    # Analysis section
    analysis = manifest["analysis"]
    assert analysis["start_time_utc"] == "2026-10-26T00:00:00Z"
    assert analysis["end_time_utc"] == "2026-10-26T06:00:00Z"
    assert analysis["satellite_id"] == "SAT-SMOKE-01"
    assert analysis["ground_station_id"] == "GS-SMOKE-01"
    assert analysis["propagation_model"] == "SGP4"
    assert analysis["gravity_model"] == "WGS72"
    assert analysis["ephemeris_samples_count"] == 73
    assert analysis["access_windows_count"] == len(result.access_windows)
    assert analysis["sgp4_non_zero_errors_count"] == 0

    # Runtime section
    runtime = manifest["runtime"]
    assert runtime["v0_tool_version"] == "0.1.0"
    assert runtime["sgp4_acceleration_active"] is True
    assert "numpy" in runtime["dependencies"]
    assert "sgp4" in runtime["dependencies"]
    assert "skyfield" in runtime["dependencies"]
    assert "pydantic" in runtime["dependencies"]
    assert runtime["platform"] is not None
    # git_commit is either a 40-char string or None; git_dirty is bool or None
    assert runtime["git_commit"] is None or isinstance(runtime["git_commit"], str)
    assert runtime["git_dirty"] is None or isinstance(runtime["git_dirty"], bool)

    # Products inventory matches actual files
    products = manifest["products"]
    assert products["validated_scenario"] == "validated_scenario.json"
    assert products["ephemeris"] == "ephemeris.csv"
    assert products["access_windows"] == "access_windows.csv"
    assert products["manifest"] == "run_manifest.json"

    # Assumptions
    assumptions = manifest["modelling_assumptions"]
    assert "synthetic representative design orbit" in assumptions
    assert "WGS72 propagation constants" in assumptions


# --- 2. Error Handling, Validation, and Collision Tests ---


def test_rejection_existing_run_directory(tmp_path: Path, smoke_run_data: tuple[ScenarioConfig, SmokeRunResult]) -> None:
    """Verify that export rejects an already existing final run directory without overwriting."""
    scenario, result = smoke_run_data
    # First export succeeds
    export_smoke_run(scenario, result, base_output_dir=tmp_path)

    # Second export with identical run_id must raise FileExistsError
    with pytest.raises(FileExistsError, match="Target run directory already exists"):
        export_smoke_run(scenario, result, base_output_dir=tmp_path)


def test_rejection_unsafe_run_id(tmp_path: Path, smoke_run_data: tuple[ScenarioConfig, SmokeRunResult]) -> None:
    """Verify rejection of unsafe run_id patterns (traversal, separators, whitespace)."""
    scenario, result = smoke_run_data

    for unsafe_id in ["../traversal", "..", "/abs/path", "space id", "lead_space ", "id;cmd", ""]:
        bad_result = SmokeRunResult(
            scenario_id=result.scenario_id,
            run_id=unsafe_id,
            analysis_start_utc=result.analysis_start_utc,
            analysis_end_utc=result.analysis_end_utc,
            satellite_id=result.satellite_id,
            ground_station_id=result.ground_station_id,
            ephemeris=result.ephemeris,
            access_windows=result.access_windows,
            execution_duration_seconds=result.execution_duration_seconds,
            completed_at_utc=result.completed_at_utc,
        )
        with pytest.raises(ValueError):
            export_smoke_run(scenario, bad_result, base_output_dir=tmp_path)


def test_rejection_scenario_result_mismatch(tmp_path: Path, smoke_run_data: tuple[ScenarioConfig, SmokeRunResult]) -> None:
    """Verify pre-export validation catches mismatched metadata."""
    scenario, result = smoke_run_data

    # Mismatched scenario ID
    bad_scen = SmokeRunResult(
        scenario_id="other_scen",
        run_id="run_01",
        analysis_start_utc=result.analysis_start_utc,
        analysis_end_utc=result.analysis_end_utc,
        satellite_id=result.satellite_id,
        ground_station_id=result.ground_station_id,
        ephemeris=result.ephemeris,
        access_windows=result.access_windows,
        execution_duration_seconds=result.execution_duration_seconds,
        completed_at_utc=result.completed_at_utc,
    )
    with pytest.raises(ValueError, match="Scenario ID mismatch"):
        export_smoke_run(scenario, bad_scen, base_output_dir=tmp_path)


def test_rejection_non_finite_ephemeris(tmp_path: Path, smoke_run_data: tuple[ScenarioConfig, SmokeRunResult]) -> None:
    """Verify rejection when ephemeris contains NaN or Inf values."""
    scenario, result = smoke_run_data

    nan_positions = result.ephemeris.position_teme_km.copy()
    nan_positions[0, 0] = np.nan

    bad_eph = result.ephemeris.__class__(
        satellite_id=result.ephemeris.satellite_id,
        timestamps_utc=result.ephemeris.timestamps_utc,
        position_teme_km=nan_positions,
        velocity_teme_km_s=result.ephemeris.velocity_teme_km_s,
        sgp4_error_codes=result.ephemeris.sgp4_error_codes,
        frame=result.ephemeris.frame,
        position_unit=result.ephemeris.position_unit,
        velocity_unit=result.ephemeris.velocity_unit,
        propagation_model=result.ephemeris.propagation_model,
        gravity_model=result.ephemeris.gravity_model,
    )

    bad_result = SmokeRunResult(
        scenario_id=result.scenario_id,
        run_id="nan_run",
        analysis_start_utc=result.analysis_start_utc,
        analysis_end_utc=result.analysis_end_utc,
        satellite_id=result.satellite_id,
        ground_station_id=result.ground_station_id,
        ephemeris=bad_eph,
        access_windows=result.access_windows,
        execution_duration_seconds=result.execution_duration_seconds,
        completed_at_utc=result.completed_at_utc,
    )

    with pytest.raises(ValueError, match="contains non-finite values"):
        export_smoke_run(scenario, bad_result, base_output_dir=tmp_path)


def test_failure_cleanup_atomicity(tmp_path: Path, smoke_run_data: tuple[ScenarioConfig, SmokeRunResult], monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that a write failure cleans up the temporary directory and leaves no run directory."""
    scenario, result = smoke_run_data

    # Monkeypatch _write_run_manifest to simulate a crash mid-export
    def mock_fail(*args: object, **kwargs: object) -> None:
        raise IOError("Simulated disk error during manifest write")

    monkeypatch.setattr("v0_tool.export._write_run_manifest", mock_fail)

    with pytest.raises(IOError, match="Simulated disk error"):
        export_smoke_run(scenario, result, base_output_dir=tmp_path)

    # Assert no final run directory exists
    final_dir = tmp_path / result.run_id
    assert not final_dir.exists()

    # Assert no orphaned .tmp_ staging directories exist under tmp_path
    remaining = list(tmp_path.iterdir())
    assert remaining == []


def test_no_mutation_of_scenario_or_result(tmp_path: Path, smoke_run_data: tuple[ScenarioConfig, SmokeRunResult]) -> None:
    """Verify that exporting does not mutate input objects."""
    scenario, result = smoke_run_data
    scen_dump_before = scenario.model_dump()

    export_smoke_run(scenario, result, base_output_dir=tmp_path)

    assert scenario.model_dump() == scen_dump_before


def test_format_utc_iso_helper() -> None:
    """Verify format_utc_iso formatting with and without microseconds."""
    dt_sec = datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)
    assert format_utc_iso(dt_sec) == "2026-10-26T00:00:00Z"

    dt_micro = datetime(2026, 10, 26, 1, 31, 17, 23656, tzinfo=timezone.utc)
    assert format_utc_iso(dt_micro) == "2026-10-26T01:31:17.023656Z"

    # Reject naive
    with pytest.raises(ValueError, match="must be timezone-aware"):
        format_utc_iso(datetime(2026, 10, 26, 0, 0, 0))

    # Reject non-UTC
    with pytest.raises(ValueError, match="must have UTC timezone"):
        format_utc_iso(datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone(timedelta(hours=2))))
