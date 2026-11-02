"""Unit and CLI invocation tests for v0_tool.__main__."""

from pathlib import Path
import sys

import pytest
import yaml

from v0_tool.__main__ import main
from v0_tool.config import load_scenario

SMOKE_YAML_PATH = Path(__file__).resolve().parent.parent / "scenarios" / "smoke_01.yaml"


def test_cli_successful_invocation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Verify successful CLI execution using a temporary scenario targeting tmp_path."""
    # Create temporary scenario pointing output_dir beneath tmp_path
    sc = load_scenario(SMOKE_YAML_PATH)
    sc_dict = sc.model_dump()
    target_output_base = tmp_path / "custom_outputs"
    sc_dict["output"]["output_dir"] = str(target_output_base)

    temp_scenario_yaml = tmp_path / "temp_smoke.yaml"
    with open(temp_scenario_yaml, "w", encoding="utf-8") as f:
        yaml.dump(sc_dict, f)

    # Invoke CLI main
    exit_code = main([str(temp_scenario_yaml)])

    assert exit_code == 0

    captured = capsys.readouterr()
    stdout = captured.out
    stderr = captured.err

    assert stderr == ""
    assert "Smoke workflow completed successfully." in stdout
    assert "Scenario ID:         smoke_01" in stdout
    assert "Run ID:              smoke_01_" in stdout
    assert "Ephemeris samples:   73" in stdout
    assert "Access windows:      1" in stdout
    assert "Execution duration:" in stdout
    assert "Output directory:" in stdout

    # Confirm products were exported beneath target_output_base, not real repository outputs
    assert target_output_base.is_dir()
    run_dirs = [p for p in target_output_base.iterdir() if p.is_dir()]
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    assert (run_dir / "validated_scenario.json").is_file()
    assert (run_dir / "ephemeris.csv").is_file()
    assert (run_dir / "access_windows.csv").is_file()
    assert (run_dir / "run_manifest.json").is_file()


def test_cli_missing_scenario_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Verify non-zero exit and concise stderr message on non-existent scenario path."""
    non_existent = tmp_path / "does_not_exist.yaml"
    exit_code = main([str(non_existent)])

    assert exit_code == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Error:" in captured.err
    assert "not found" in captured.err
    # Verify no Python traceback was printed
    assert "Traceback" not in captured.err


def test_cli_missing_argument(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify argparse error and exit code 2 when scenario argument is omitted."""
    with pytest.raises(SystemExit) as exc_info:
        main([])

    assert exc_info.value.code == 2

    captured = capsys.readouterr()
    assert "usage:" in captured.err or "usage:" in captured.out


def test_cli_validation_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Verify non-zero exit on schema validation failure."""
    bad_yaml = tmp_path / "invalid_scenario.yaml"
    bad_yaml.write_text("scenario_id: test\nsatellites: []\n", encoding="utf-8")

    exit_code = main([str(bad_yaml)])

    assert exit_code == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Error:" in captured.err
    assert "Traceback" not in captured.err
