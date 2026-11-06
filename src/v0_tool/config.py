"""Scenario configuration schema and validation for V0 mission analysis.

Stage 1 Assumption:
    In Stage 1, all satellite orbital parameters (representative circular design
    altitude, inclination, and cyclic orbital angles) are assumed to be defined
    at analysis.start_time_utc. No separate satellite epoch field is defined in
    Stage 1.

Stage 2 Evolution:
    Stage 2 supports both explicit satellite lists (for Stage 1 compatibility)
    and synthetic Walker Delta constellation definitions.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


def _validate_non_empty_string(value: str, field_name: str) -> str:
    """Validate that a string identifier is non-empty and not only whitespace."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value.strip()


class AnalysisConfig(BaseModel):
    """Configuration for analysis period and ephemeris time stepping."""

    start_time_utc: datetime = Field(
        ...,
        description="Analysis start epoch in UTC (must be timezone-aware UTC).",
    )
    end_time_utc: datetime = Field(
        ...,
        description="Analysis end epoch in UTC (must be timezone-aware UTC).",
    )
    ephemeris_interval_seconds: float = Field(
        ...,
        gt=0.0,
        description="Propagation and ephemeris output timestep in seconds.",
    )

    @field_validator("start_time_utc", "end_time_utc")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Enforce timezone awareness and explicit UTC (+00:00 or Z)."""
        if v.tzinfo is None:
            raise ValueError("Datetime must be timezone-aware.")
        offset = v.utcoffset()
        if offset is None or offset != timedelta(0):
            raise ValueError(
                f"Datetime must have UTC timezone (+00:00 or Z), got offset {offset}."
            )
        return v

    @model_validator(mode="after")
    def validate_time_order(self) -> Self:
        """Ensure end_time_utc is strictly after start_time_utc."""
        if self.end_time_utc <= self.start_time_utc:
            raise ValueError(
                f"end_time_utc ({self.end_time_utc}) must be strictly after "
                f"start_time_utc ({self.start_time_utc})."
            )
        return self

    @property
    def duration_seconds(self) -> float:
        """Calculate total scenario duration in seconds."""
        return (self.end_time_utc - self.start_time_utc).total_seconds()


class SatelliteConfig(BaseModel):
    """Configuration for a single synthetic satellite.

    Note on Stage 1 design altitude:
        altitude_km is treated as a representative circular design altitude.
        Mean motion calculation and SGP4 record construction occur in later tasks.
        Orbital angles are assumed to be defined at analysis.start_time_utc.
    """

    satellite_id: str = Field(..., description="Unique satellite identifier.")
    altitude_km: float = Field(
        ...,
        gt=0.0,
        description="Representative circular design altitude in kilometres.",
    )
    inclination_deg: float = Field(
        ...,
        ge=0.0,
        le=180.0,
        description="Orbital inclination in degrees [0, 180].",
    )
    eccentricity: float = Field(
        0.0,
        ge=0.0,
        lt=1.0,
        description="Orbital eccentricity [0, 1). Defaults to 0.0 for circular design orbit.",
    )
    raan_deg: float = Field(
        0.0,
        ge=0.0,
        lt=360.0,
        description="Right ascension of ascending node in degrees [0, 360).",
    )
    arg_perigee_deg: float = Field(
        0.0,
        ge=0.0,
        lt=360.0,
        description="Argument of perigee in degrees [0, 360).",
    )
    mean_anomaly_deg: float = Field(
        0.0,
        ge=0.0,
        lt=360.0,
        description="Mean anomaly at epoch in degrees [0, 360).",
    )
    bstar: float = Field(
        0.0,
        description="SGP4 B* drag parameter (1/earth radii). Defaults to 0.0.",
    )

    @field_validator("satellite_id")
    @classmethod
    def validate_satellite_id(cls, v: str) -> str:
        return _validate_non_empty_string(v, "satellite_id")


class WalkerDeltaConfig(BaseModel):
    """Configuration for generating a synthetic Walker Delta constellation."""

    type: Literal["walker_delta"] = "walker_delta"
    constellation_id: str = Field(..., description="Unique constellation identifier.")
    total_satellites: int = Field(..., gt=0, description="Total number of satellites (T).")
    planes: int = Field(..., gt=0, description="Number of orbital planes (P).")
    phasing: int = Field(..., ge=0, description="Walker phasing parameter (F), 0 <= F < P.")
    altitude_km: float = Field(
        ...,
        gt=0.0,
        description="Representative circular design altitude in kilometres.",
    )
    inclination_deg: float = Field(
        ...,
        ge=0.0,
        le=180.0,
        description="Orbital inclination in degrees [0, 180].",
    )
    eccentricity: float = Field(
        0.0,
        ge=0.0,
        lt=1.0,
        description="Orbital eccentricity [0, 1). Defaults to 0.0 for circular design orbit.",
    )
    raan_origin_deg: float = Field(
        0.0,
        ge=0.0,
        lt=360.0,
        description="RAAN origin in degrees [0, 360).",
    )
    mean_anomaly_origin_deg: float = Field(
        0.0,
        ge=0.0,
        lt=360.0,
        description="Mean anomaly origin in degrees [0, 360).",
    )
    arg_perigee_deg: float = Field(
        0.0,
        ge=0.0,
        lt=360.0,
        description="Argument of perigee in degrees [0, 360).",
    )
    bstar: float = Field(
        0.0,
        description="SGP4 B* drag parameter (1/earth radii). Defaults to 0.0.",
    )

    @field_validator("constellation_id")
    @classmethod
    def validate_constellation_id(cls, v: str) -> str:
        return _validate_non_empty_string(v, "constellation_id")

    @model_validator(mode="after")
    def validate_walker_parameters(self) -> Self:
        """Validate divisibility and phasing parameter constraints."""
        if self.total_satellites % self.planes != 0:
            raise ValueError(
                f"total_satellites ({self.total_satellites}) must be divisible by planes ({self.planes})."
            )
        if self.phasing >= self.planes:
            raise ValueError(
                f"phasing parameter F ({self.phasing}) must be strictly less than planes P ({self.planes})."
            )
        return self


class GroundStationConfig(BaseModel):
    """Configuration for a fixed ground station or gateway."""

    station_id: str = Field(..., description="Unique ground station identifier.")
    latitude_deg: float = Field(
        ...,
        ge=-90.0,
        le=90.0,
        description="Geodetic latitude in degrees [-90, 90].",
    )
    longitude_deg: float = Field(
        ...,
        ge=-180.0,
        le=180.0,
        description="Geodetic longitude in degrees [-180, 180].",
    )
    altitude_m: float = Field(
        0.0,
        ge=-500.0,
        description="Altitude above WGS84 ellipsoid in metres (>= -500.0 m).",
    )
    minimum_elevation_deg: float = Field(
        10.0,
        ge=0.0,
        le=90.0,
        description="Minimum elevation mask in degrees [0, 90].",
    )

    @field_validator("station_id")
    @classmethod
    def validate_station_id(cls, v: str) -> str:
        return _validate_non_empty_string(v, "station_id")


class OutputConfig(BaseModel):
    """Configuration for output directory destination."""

    output_dir: Path = Field(
        ...,
        description="Target directory path for generated output products.",
    )


class ScenarioConfig(BaseModel):
    """Root configuration model for a V0 mission analysis scenario."""

    scenario_id: str = Field(..., description="Unique scenario identifier.")
    analysis: AnalysisConfig
    satellites: list[SatelliteConfig] = Field(
        default_factory=list,
        description="Explicit list of satellites.",
    )
    constellation: WalkerDeltaConfig | None = Field(
        default=None,
        description="Synthetic Walker Delta constellation configuration.",
    )
    ground_stations: list[GroundStationConfig] = Field(
        ...,
        min_length=1,
        description="List of ground stations (at least one required).",
    )
    output: OutputConfig

    @field_validator("scenario_id")
    @classmethod
    def validate_scenario_id(cls, v: str) -> str:
        return _validate_non_empty_string(v, "scenario_id")

    @model_validator(mode="after")
    def validate_satellite_source_and_identifiers(self) -> Self:
        """Enforce exactly one satellite source and unique identifiers."""
        has_satellites = len(self.satellites) > 0
        has_constellation = self.constellation is not None

        if has_satellites and has_constellation:
            raise ValueError(
                "Scenario must define either explicit 'satellites' or a 'constellation', not both."
            )
        if not has_satellites and not has_constellation:
            raise ValueError(
                "Scenario must define either at least one explicit satellite or a 'constellation'."
            )

        # Enforce unique identifiers when explicit satellites are supplied
        if has_satellites:
            sat_ids = [sat.satellite_id for sat in self.satellites]
            if len(sat_ids) != len(set(sat_ids)):
                raise ValueError(
                    f"Duplicate satellite_id detected in satellites list: {sat_ids}"
                )

        station_ids = [gs.station_id for gs in self.ground_stations]
        if len(station_ids) != len(set(station_ids)):
            raise ValueError(
                f"Duplicate station_id detected in ground_stations list: {station_ids}"
            )
        return self


def load_scenario(path: Path | str) -> ScenarioConfig:
    """Load and validate a scenario YAML file without side effects.

    Args:
        path: Path to the YAML scenario file.

    Returns:
        Validated ScenarioConfig instance.

    Raises:
        FileNotFoundError: If the specified file does not exist.
        ValueError: If YAML does not parse into a valid dictionary mapping.
        pydantic.ValidationError: If validation fails.
    """
    path_obj = Path(path)
    if not path_obj.is_file():
        raise FileNotFoundError(f"Scenario configuration file not found: {path_obj}")

    with open(path_obj, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(
            f"Scenario file '{path_obj}' does not contain a valid mapping/dictionary."
        )

    return ScenarioConfig.model_validate(data)
