"""CLI entry point for running the V0 mission-analysis smoke test.

Usage:
    python -m v0_tool <scenario_yaml_path>
"""

import argparse
from pathlib import Path
import sys

from pydantic import ValidationError

from v0_tool.access import AccessEventSequenceError
from v0_tool.config import load_scenario
from v0_tool.export import export_smoke_run
from v0_tool.propagation import Sgp4PropagationError
from v0_tool.workflow import SmokeWorkflowConfigurationError, run_smoke_workflow


def main(args: list[str] | None = None) -> int:
    """Execute the smoke workflow CLI command."""
    parser = argparse.ArgumentParser(
        prog="python -m v0_tool",
        description="Run the V0 satellite mission-analysis smoke workflow.",
    )
    parser.add_argument(
        "scenario_path",
        type=Path,
        help="Path to the scenario YAML configuration file.",
    )

    parsed_args = parser.parse_args(args)
    scenario_path: Path = parsed_args.scenario_path

    try:
        # 1. Load scenario
        scenario = load_scenario(scenario_path)

        # 2. Run workflow
        result = run_smoke_workflow(scenario)

        # 3. Export products to configured output directory
        export_res = export_smoke_run(scenario, result)

        # 4. Concise success summary to stdout
        print("Smoke workflow completed successfully.")
        print(f"Scenario ID:         {result.scenario_id}")
        print(f"Run ID:              {result.run_id}")
        print(f"Ephemeris samples:   {len(result.ephemeris.timestamps_utc)}")
        print(f"Access windows:      {len(result.access_windows)}")
        print(f"Execution duration:  {result.execution_duration_seconds:.4f} s")
        print(f"Output directory:    {export_res.output_directory}")
        return 0

    except (
        FileNotFoundError,
        ValueError,
        ValidationError,
        SmokeWorkflowConfigurationError,
        Sgp4PropagationError,
        AccessEventSequenceError,
        FileExistsError,
    ) as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1
    except Exception as e:
        sys.stderr.write(f"Unexpected error: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
