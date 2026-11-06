"""Focused unit tests for scenario configuration and validation (Stage 1 Task 2)."""

from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from v0_tool.config import (
    AnalysisConfig,
    GroundStationConfig,
    OutputConfig,
    SatelliteConfig,
    ScenarioConfig,
    load_scenario,
)


def _valid_base_dict() -> dict:
    """Return a valid minimal scenario dictionary."""
    return {
        "scenario_id": "test_scenario",
        "analysis": {
            "start_time_utc": "2026-10-26T00:00:00Z",
            "end_time_utc": "2026-10-26T06:00:00Z",
            "ephemeris_interval_seconds": 300.0,
        },
        "satellites": [
            {
                "satellite_id": "SAT-01",
                "altitude_km": 550.0,
                "inclination_deg": 53.0,
                "eccentricity": 0.0,
                "raan_deg": 0.0,
                "arg_perigee_deg": 0.0,
                "mean_anomaly_deg": 0.0,
                "bstar": 0.0,
            }
        ],
        "ground_stations": [
            {
                "station_id": "GS-01",
                "latitude_deg": 0.0,
                "longitude_deg": 0.0,
                "altitude_m": 0.0,
                "minimum_elevation_deg": 10.0,
            }
        ],
        "output": {
            "output_dir": "outputs/test_run",
        },
    }


def test_load_smoke_01_yaml() -> None:
    """Verify successful loading, validation, and contents of smoke_01.yaml."""
    yaml_path = Path(__file__).resolve().parent.parent / "scenarios" / "smoke_01.yaml"
    scenario = load_scenario(yaml_path)

    # Validate root ID
    assert scenario.scenario_id == "smoke_01"

    # Validate Stage 1 smoke test counts (exactly one of each)
    assert len(scenario.satellites) == 1
    assert len(scenario.ground_stations) == 1
    assert scenario.satellites[0].satellite_id == "SAT-SMOKE-01"
    assert scenario.ground_stations[0].station_id == "GS-SMOKE-01"

    # Validate duration of 21,600 seconds (6 hours)
    assert scenario.analysis.duration_seconds == 21600.0

    # Validate UTC-aware timestamps with zero offset
    assert scenario.analysis.start_time_utc.tzinfo is not None
    assert scenario.analysis.start_time_utc.utcoffset() == timedelta(0)
    assert scenario.analysis.end_time_utc.tzinfo is not None
    assert scenario.analysis.end_time_utc.utcoffset() == timedelta(0)
    assert scenario.analysis.start_time_utc == datetime(2026, 10, 26, 0, 0, 0, tzinfo=timezone.utc)
    assert scenario.analysis.end_time_utc == datetime(2026, 10, 26, 6, 0, 0, tzinfo=timezone.utc)


def test_no_output_dir_side_effect_on_validation(tmp_path: Path) -> None:
    """Verify that validating or loading scenario config does not create output_dir on disk."""
    data = _valid_base_dict()
    non_existent_output_dir = tmp_path / "nested" / "output_dir"
    data["output"]["output_dir"] = str(non_existent_output_dir)

    assert not non_existent_output_dir.exists()

    # Model validation must not create directory
    scenario = ScenarioConfig.model_validate(data)
    assert scenario.output.output_dir == non_existent_output_dir
    assert not non_existent_output_dir.exists()

    # load_scenario must not create directory
    scenario_yaml = tmp_path / "scenario.yaml"
    with open(scenario_yaml, "w", encoding="utf-8") as f:
        yaml.dump(data, f)

    loaded_scenario = load_scenario(scenario_yaml)
    assert loaded_scenario.output.output_dir == non_existent_output_dir
    assert not non_existent_output_dir.exists()


def test_empty_identifiers() -> None:
    """Verify rejection of empty or whitespace-only identifiers."""
    data = _valid_base_dict()

    # Empty scenario_id
    data["scenario_id"] = "   "
    with pytest.raises(ValidationError, match="scenario_id must be a non-empty string"):
        ScenarioConfig.model_validate(data)
    data["scenario_id"] = "valid_scenario"

    # Empty satellite_id
    data["satellites"][0]["satellite_id"] = ""
    with pytest.raises(ValidationError, match="satellite_id must be a non-empty string"):
        ScenarioConfig.model_validate(data)
    data["satellites"][0]["satellite_id"] = "SAT-01"

    # Empty station_id
    data["ground_stations"][0]["station_id"] = " \t "
    with pytest.raises(ValidationError, match="station_id must be a non-empty string"):
        ScenarioConfig.model_validate(data)


def test_duplicate_satellite_ids() -> None:
    """Verify rejection of duplicate satellite IDs."""
    data = _valid_base_dict()
    data["satellites"].append(
        {
            "satellite_id": "SAT-01",  # duplicate ID
            "altitude_km": 600.0,
            "inclination_deg": 45.0,
        }
    )
    with pytest.raises(ValidationError, match="Duplicate satellite_id detected"):
        ScenarioConfig.model_validate(data)


def test_duplicate_station_ids() -> None:
    """Verify rejection of duplicate ground station IDs."""
    data = _valid_base_dict()
    data["ground_stations"].append(
        {
            "station_id": "GS-01",  # duplicate ID
            "latitude_deg": 52.0,
            "longitude_deg": 4.0,
            "altitude_m": 10.0,
            "minimum_elevation_deg": 10.0,
        }
    )
    with pytest.raises(ValidationError, match="Duplicate station_id detected"):
        ScenarioConfig.model_validate(data)


def test_invalid_time_ordering() -> None:
    """Verify rejection when end time is not strictly after start time."""
    data = _valid_base_dict()

    # Equal start and end time
    data["analysis"]["end_time_utc"] = "2026-10-26T00:00:00Z"
    with pytest.raises(ValidationError, match="must be strictly after start_time_utc"):
        ScenarioConfig.model_validate(data)

    # End time before start time
    data["analysis"]["end_time_utc"] = "2026-10-25T23:59:59Z"
    with pytest.raises(ValidationError, match="must be strictly after start_time_utc"):
        ScenarioConfig.model_validate(data)


def test_naive_and_non_utc_timestamps() -> None:
    """Verify rejection of naive datetimes and non-UTC offsets."""
    data = _valid_base_dict()

    # Naive start time (no timezone offset)
    data["analysis"]["start_time_utc"] = "2026-10-26T00:00:00"
    with pytest.raises(ValidationError, match="Datetime must be timezone-aware"):
        ScenarioConfig.model_validate(data)

    # Non-UTC timezone offset (+02:00)
    data["analysis"]["start_time_utc"] = "2026-10-26T02:00:00+02:00"
    with pytest.raises(ValidationError, match="Datetime must have UTC timezone"):
        ScenarioConfig.model_validate(data)

    # Explicit +00:00 offset is accepted
    data["analysis"]["start_time_utc"] = "2026-10-26T00:00:00+00:00"
    cfg = ScenarioConfig.model_validate(data)
    assert cfg.analysis.start_time_utc.utcoffset() == timedelta(0)


def test_ephemeris_interval() -> None:
    """Verify rejection of zero or negative ephemeris intervals."""
    data = _valid_base_dict()

    data["analysis"]["ephemeris_interval_seconds"] = 0.0
    with pytest.raises(ValidationError):
        ScenarioConfig.model_validate(data)

    data["analysis"]["ephemeris_interval_seconds"] = -10.0
    with pytest.raises(ValidationError):
        ScenarioConfig.model_validate(data)


def test_invalid_latitude_and_longitude() -> None:
    """Verify rejection of out-of-range geodetic latitude and longitude."""
    data = _valid_base_dict()

    # Latitude < -90 or > 90
    data["ground_stations"][0]["latitude_deg"] = -90.001
    with pytest.raises(ValidationError):
        ScenarioConfig.model_validate(data)

    data["ground_stations"][0]["latitude_deg"] = 90.001
    with pytest.raises(ValidationError):
        ScenarioConfig.model_validate(data)
    data["ground_stations"][0]["latitude_deg"] = 0.0

    # Longitude < -180 or > 180
    data["ground_stations"][0]["longitude_deg"] = -180.001
    with pytest.raises(ValidationError):
        ScenarioConfig.model_validate(data)

    data["ground_stations"][0]["longitude_deg"] = 180.001
    with pytest.raises(ValidationError):
        ScenarioConfig.model_validate(data)


def test_invalid_inclination() -> None:
    """Verify rejection of inclination outside [0, 180] degrees."""
    data = _valid_base_dict()

    data["satellites"][0]["inclination_deg"] = -0.01
    with pytest.raises(ValidationError):
        ScenarioConfig.model_validate(data)

    data["satellites"][0]["inclination_deg"] = 180.01
    with pytest.raises(ValidationError):
        ScenarioConfig.model_validate(data)

    # Boundaries 0 and 180 are valid
    data["satellites"][0]["inclination_deg"] = 0.0
    assert ScenarioConfig.model_validate(data).satellites[0].inclination_deg == 0.0

    data["satellites"][0]["inclination_deg"] = 180.0
    assert ScenarioConfig.model_validate(data).satellites[0].inclination_deg == 180.0


def test_orbital_angles_range() -> None:
    """Verify rejection of cyclic orbital angles >= 360 or < 0 (half-open [0, 360))."""
    data = _valid_base_dict()

    for angle_field in ["raan_deg", "arg_perigee_deg", "mean_anomaly_deg"]:
        # Exactly 360 is rejected (half-open interval)
        data["satellites"][0][angle_field] = 360.0
        with pytest.raises(ValidationError):
            ScenarioConfig.model_validate(data)

        # > 360 is rejected
        data["satellites"][0][angle_field] = 360.1
        with pytest.raises(ValidationError):
            ScenarioConfig.model_validate(data)

        # < 0 is rejected
        data["satellites"][0][angle_field] = -0.1
        with pytest.raises(ValidationError):
            ScenarioConfig.model_validate(data)

        # Reset to valid
        data["satellites"][0][angle_field] = 0.0


def test_eccentricity_range() -> None:
    """Verify rejection of eccentricity outside [0, 1)."""
    data = _valid_base_dict()

    # Negative eccentricity
    data["satellites"][0]["eccentricity"] = -0.01
    with pytest.raises(ValidationError):
        ScenarioConfig.model_validate(data)

    # Parabolic (1.0) rejected
    data["satellites"][0]["eccentricity"] = 1.0
    with pytest.raises(ValidationError):
        ScenarioConfig.model_validate(data)

    # Hyperbolic (> 1.0) rejected
    data["satellites"][0]["eccentricity"] = 1.2
    with pytest.raises(ValidationError):
        ScenarioConfig.model_validate(data)


def test_elevation_range() -> None:
    """Verify rejection of minimum elevation outside [0, 90] degrees."""
    data = _valid_base_dict()

    data["ground_stations"][0]["minimum_elevation_deg"] = -0.01
    with pytest.raises(ValidationError):
        ScenarioConfig.model_validate(data)

    data["ground_stations"][0]["minimum_elevation_deg"] = 90.01
    with pytest.raises(ValidationError):
        ScenarioConfig.model_validate(data)

    # Boundaries 0 and 90 are valid
    data["ground_stations"][0]["minimum_elevation_deg"] = 0.0
    assert ScenarioConfig.model_validate(data).ground_stations[0].minimum_elevation_deg == 0.0

    data["ground_stations"][0]["minimum_elevation_deg"] = 90.0
    assert ScenarioConfig.model_validate(data).ground_stations[0].minimum_elevation_deg == 90.0


def test_empty_lists() -> None:
    """Verify rejection when satellite or ground-station lists are empty."""
    data = _valid_base_dict()

    data["satellites"] = []
    with pytest.raises(ValidationError):
        ScenarioConfig.model_validate(data)
    data["satellites"] = _valid_base_dict()["satellites"]

    data["ground_stations"] = []
    with pytest.raises(ValidationError):
        ScenarioConfig.model_validate(data)


def test_load_scenario_file_errors(tmp_path: Path) -> None:
    """Verify FileNotFoundError and ValueError on invalid scenario paths and non-mapping YAML."""
    # Non-existent file
    with pytest.raises(FileNotFoundError, match="not found"):
        load_scenario("non_existent_file.yaml")

    # Non-mapping YAML content (e.g., scalar or list)
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not contain a valid mapping/dictionary"):
        load_scenario(bad_yaml)


def test_load_poc_01_yaml() -> None:
    """Verify loading and validation of scenarios/poc_01.yaml."""
    yaml_path = Path(__file__).resolve().parent.parent / "scenarios" / "poc_01.yaml"
    scenario = load_scenario(yaml_path)

    assert scenario.scenario_id == "poc_01"
    assert scenario.constellation is not None
    assert scenario.satellites == []
    assert scenario.constellation.type == "walker_delta"
    assert scenario.constellation.constellation_id == "WALKER-6-3-1"
    assert scenario.constellation.total_satellites == 6
    assert scenario.constellation.planes == 3
    assert scenario.constellation.phasing == 1

    # Exactly two ground stations
    assert len(scenario.ground_stations) == 2
    station_ids = [gs.station_id for gs in scenario.ground_stations]
    assert station_ids == ["GS-EQUATOR", "GS-MIDLAT"]

    # Duration 86,400s (24 hours) and 60s timestep
    assert scenario.analysis.duration_seconds == 86400.0
    assert scenario.analysis.ephemeris_interval_seconds == 60.0

    # Expected future inclusive sample count: 86400 / 60 + 1 = 1,441
    expected_sample_count = int(scenario.analysis.duration_seconds / scenario.analysis.ephemeris_interval_seconds) + 1
    assert expected_sample_count == 1441


def test_scenario_satellite_source_mutual_exclusivity() -> None:
    """Verify rejection when both or neither satellite sources are specified."""
    data = _valid_base_dict()

    walker_dict = {
        "type": "walker_delta",
        "constellation_id": "W-TEST",
        "total_satellites": 6,
        "planes": 2,
        "phasing": 1,
        "altitude_km": 550.0,
        "inclination_deg": 53.0,
    }

    # Both explicit satellites and constellation populated -> Rejected
    data["constellation"] = walker_dict
    with pytest.raises(ValidationError, match="not both"):
        ScenarioConfig.model_validate(data)

    # Neither populated (satellites empty, constellation None) -> Rejected
    data["satellites"] = []
    data["constellation"] = None
    with pytest.raises(ValidationError, match="either at least one explicit satellite or a 'constellation'"):
        ScenarioConfig.model_validate(data)

    # Constellation only (satellites empty list) -> Accepted
    data["constellation"] = walker_dict
    cfg = ScenarioConfig.model_validate(data)
    assert cfg.constellation is not None
    assert cfg.satellites == []
