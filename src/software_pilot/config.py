"""Pilot configuration schema using Pydantic."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator


class PilotConfig(BaseModel):
    """Configuration for the software pilot at startup.

    Attributes:
        drone_id: Unique identifier for this drone (0-based index)
        mavsdk_port: gRPC port for MAVSDK autopilot communication
        mavlink_port: UDP port for MAVLink protocol (for GCS/routing)
        sade_zone_config_path: Path to SADE zone configuration JSON
        mqtt_broker_address: Address of MQTT broker (e.g., "localhost:1883")
        custom_settings: User-provided custom mission configuration
    """

    drone_id: int = Field(..., gt=-1, description="Drone identifier (0-based)")
    mavsdk_port: int = Field(
        default=14550,
        ge=1024,
        le=65535,
        description="gRPC port for MAVSDK autopilot",
    )
    mavlink_port: int = Field(
        default=14540,
        ge=1024,
        le=65535,
        description="UDP port for MAVLink protocol",
    )
    sade_zone_config_path: Path | None = Field(
        default=None,
        description="Path to SADE zone configuration JSON file",
    )
    mqtt_broker_address: str = Field(
        default="localhost:1883",
        description="MQTT broker address (host:port)",
    )
    custom_settings: dict[str, Any] = Field(
        default_factory=dict,
        description="User-provided custom mission settings",
    )

    @model_validator(mode="after")
    def validate_paths(self) -> "PilotConfig":
        """Validate that provided paths exist."""
        if self.sade_zone_config_path is not None:
            path = Path(self.sade_zone_config_path)
            if not path.exists():
                msg = f"SADE zone config not found: {path}"
                raise ValueError(msg)
        return self

    def model_dump_json_custom(self) -> str:
        """Export config as JSON (excluding Paths for serialization)."""
        data = self.model_dump()
        if data.get("sade_zone_config_path"):
            data["sade_zone_config_path"] = str(data["sade_zone_config_path"])
        return json.dumps(data)


# Backward compatibility: alias for old config access patterns
PilotSettings = PilotConfig
