"""Unit and integration tests for the Stage 1 smoke workflow orchestrator.

Note on testing scope:
    Tests verify the workflow orchestration sequence, contract guarantees, timing,
    run ID policy, rejection rules, immutability, and deterministic reproducibility.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pytest

from v0_tool.access import AccessWindow
from v0_tool.config import GroundStationConfig, SatelliteConfig, ScenarioConfig, load_scenario
from v0_tool.propagation import EphemerisProduct
from v0_tool.workflow import (
    SmokeRunResult,
    SmokeWorkflowConfigurationError,
    generate_run_id,
    run_smoke_workflow,
)
import yaml

SMOKE_YAML_PATH = Path(__file__).resolve().parent.parent / "scenarios" / "smoke_01.yaml"


def test_generate_run_id_format() -> None:
    """Verify format: <scenario_id>_<full uuid4 hex> (32 hex characters after prefix)."""
    run_id = generate_run_id("test_scen")
    assert run_id.startswith("test_scen_")
    hex_part = run_id[len("test_scen_"):]
    assert len(hex_part) == 32
    # Verify valid hex
    int(hex_part, 16)


def test_smoke_workflow_execution_from_path() -> None:
    """Verify complete execution from a Path object with contract checks."""
    result = run_smoke_workflow(SMOKE_YAML_PATH)

    assert isinstance(result, SmokeRunResult)
    assert result.scenario_id == "smoke_01"
    assert result.satellite_id == "SAT-SMOKE-01"
    assert result.ground_station_id == "GS-SMOKE-01"
    assert result.run_id.startswith("smoke_01_")

    # Time bounds
    assert result.analysis_start_utc == datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)
    assert result.analysis_end_utc == datetime(2026, 10, 26, 6, 0, 0, tzinfo=timezone.utc)

    # Ephemeris contracts
    assert isinstance(result.ephemeris, EphemerisProduct)
    assert len(result.ephemeris.timestamps_utc) == 73
    assert result.ephemeris.position_teme_km.shape == (73, 3)
    assert result.ephemeris.velocity_teme_km_s.shape == (73, 3)
    assert np.all(result.ephemeris.sgp4_error_codes == 0)

    # Access window contracts
    assert isinstance(result.access_windows, tuple)
    assert len(result.access_windows) >= 1
    for w in result.access_windows:
        assert isinstance(w, AccessWindow)
        assert w.duration_seconds > 0.0
        assert result.analysis_start_utc <= w.start_time_utc < w.end_time_utc <= result.analysis_end_utc

    # Timing properties
    assert result.execution_duration_seconds >= 0.0
    assert result.completed_at_utc.tzinfo is not None
    assert result.completed_at_utc.utcoffset() == timedelta(0)


def test_smoke_workflow_input_types() -> None:
    """Verify workflow accepts Path, str, and pre-loaded ScenarioConfig identically."""
    # From str path
    res_str = run_smoke_workflow(str(SMOKE_YAML_PATH), run_id="fixed_run_str")
    assert res_str.run_id == "fixed_run_str"
    assert len(res_str.ephemeris.timestamps_utc) == 73

    # From ScenarioConfig
    sc = load_scenario(SMOKE_YAML_PATH)
    res_sc = run_smoke_workflow(sc, run_id="fixed_run_sc")
    assert res_sc.run_id == "fixed_run_sc"
    assert len(res_sc.ephemeris.timestamps_utc) == 73


def test_explicit_run_id_validation() -> None:
    """Verify preservation of valid explicit run_id and rejection of invalid ones."""
    # Valid explicit run_id
    res = run_smoke_workflow(SMOKE_YAML_PATH, run_id="my_custom_run_01")
    assert res.run_id == "my_custom_run_01"

    # Empty string
    with pytest.raises(ValueError, match="must not be empty or whitespace-only"):
        run_smoke_workflow(SMOKE_YAML_PATH, run_id="")

    # Whitespace-only string
    with pytest.raises(ValueError, match="must not be empty or whitespace-only"):
        run_smoke_workflow(SMOKE_YAML_PATH, run_id="   \t  ")

    # Leading whitespace
    with pytest.raises(ValueError, match="must not contain leading or trailing whitespace"):
        run_smoke_workflow(SMOKE_YAML_PATH, run_id="  lead_space")

    # Trailing whitespace
    with pytest.raises(ValueError, match="must not contain leading or trailing whitespace"):
        run_smoke_workflow(SMOKE_YAML_PATH, run_id="trail_space  ")


def test_workflow_determinism_and_differing_metadata() -> None:
    """Verify equal scientific results across runs while run IDs differ automatically."""
    res1 = run_smoke_workflow(SMOKE_YAML_PATH)
    res2 = run_smoke_workflow(SMOKE_YAML_PATH)

    # Metadata differs
    assert res1.run_id != res2.run_id
    assert res1.completed_at_utc.tzinfo is not None
    assert res2.completed_at_utc.tzinfo is not None

    # Scientific outputs are identically equal
    assert np.array_equal(res1.ephemeris.position_teme_km, res2.ephemeris.position_teme_km)
    assert np.array_equal(res1.ephemeris.velocity_teme_km_s, res2.ephemeris.velocity_teme_km_s)
    assert np.array_equal(res1.ephemeris.sgp4_error_codes, res2.ephemeris.sgp4_error_codes)

    assert len(res1.access_windows) == len(res2.access_windows)
    for w1, w2 in zip(res1.access_windows, res2.access_windows):
        assert w1 == w2


def test_rejection_multi_satellite() -> None:
    """Verify rejection when scenario contains multiple satellites."""
    sc = load_scenario(SMOKE_YAML_PATH)
    extra_sat = sc.satellites[0].model_copy(update={"satellite_id": "SAT-EXTRA"})

    # Two satellites
    sc_two_sats = sc.model_copy(update={"satellites": [sc.satellites[0], extra_sat]})
    with pytest.raises(SmokeWorkflowConfigurationError, match="requires exactly 1 satellite; received 2"):
        run_smoke_workflow(sc_two_sats)


def test_rejection_zero_satellites() -> None:
    """Verify rejection when scenario contains zero satellites.

    Note:
        model_construct() is used here solely to construct a ScenarioConfig with
        empty satellites list, exercising the defensive workflow scope branch
        that normal schema validation prevents callers from reaching.
    """
    sc = load_scenario(SMOKE_YAML_PATH)
    sc_zero_sats = ScenarioConfig.model_construct(
        scenario_id=sc.scenario_id,
        analysis=sc.analysis,
        satellites=[],
        ground_stations=sc.ground_stations,
        output=sc.output,
    )
    with pytest.raises(SmokeWorkflowConfigurationError, match="requires exactly 1 satellite; received 0"):
        run_smoke_workflow(sc_zero_sats)


def test_rejection_multi_station() -> None:
    """Verify rejection when scenario contains multiple ground stations."""
    sc = load_scenario(SMOKE_YAML_PATH)
    extra_gs = sc.ground_stations[0].model_copy(update={"station_id": "GS-EXTRA"})

    # Two ground stations
    sc_two_gs = sc.model_copy(update={"ground_stations": [sc.ground_stations[0], extra_gs]})
    with pytest.raises(SmokeWorkflowConfigurationError, match="requires exactly 1 ground station; received 2"):
        run_smoke_workflow(sc_two_gs)


def test_rejection_zero_stations() -> None:
    """Verify rejection when scenario contains zero ground stations.

    Note:
        model_construct() is used here solely to construct a ScenarioConfig with
        empty ground_stations list, exercising the defensive workflow scope branch
        that normal schema validation prevents callers from reaching.
    """
    sc = load_scenario(SMOKE_YAML_PATH)
    sc_zero_gs = ScenarioConfig.model_construct(
        scenario_id=sc.scenario_id,
        analysis=sc.analysis,
        satellites=sc.satellites,
        ground_stations=[],
        output=sc.output,
    )
    with pytest.raises(SmokeWorkflowConfigurationError, match="requires exactly 1 ground station; received 0"):
        run_smoke_workflow(sc_zero_gs)


def test_no_mutation_of_input_scenario() -> None:
    """Verify that run_smoke_workflow does not mutate the passed ScenarioConfig."""
    sc = load_scenario(SMOKE_YAML_PATH)
    dump_before = sc.model_dump()

    run_smoke_workflow(sc)

    dump_after = sc.model_dump()
    assert dump_before == dump_after


def test_no_file_system_side_effects(tmp_path: Path) -> None:
    """Verify that run_smoke_workflow does not create the configured output directory or side files."""
    sc = load_scenario(SMOKE_YAML_PATH)
    non_existent_output_dir = tmp_path / "should_not_exist" / "output_dir"

    temp_dict = sc.model_dump()
    temp_dict["output"]["output_dir"] = str(non_existent_output_dir)

    temp_yaml_path = tmp_path / "temp_smoke_scenario.yaml"
    with open(temp_yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(temp_dict, f)

    # Initial state under tmp_path: only the temporary YAML file exists
    assert list(tmp_path.iterdir()) == [temp_yaml_path]
    assert not non_existent_output_dir.exists()

    result = run_smoke_workflow(temp_yaml_path)

    assert isinstance(result, SmokeRunResult)
    # The configured output directory must NOT have been created
    assert not non_existent_output_dir.exists()
    # No additional files or directories must have been created under tmp_path
    assert list(tmp_path.iterdir()) == [temp_yaml_path]
