"""Tests for software_pilot.config module."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from software_pilot.config import PilotConfig


class TestPilotConfigBasic:
    """Test basic PilotConfig instantiation and validation."""

    def test_minimal_config(self) -> None:
        """Test creating a config with only required fields."""
        config = PilotConfig(drone_id=0)
        assert config.drone_id == 0
        assert config.mavsdk_port == 14550
        assert config.mavlink_port == 14540
        assert config.mqtt_broker_address == "localhost:1883"
        assert config.sade_zone_config_path is None
        assert config.custom_settings == {}

    def test_all_fields_set(self) -> None:
        """Test creating a config with all fields explicitly set."""
        config = PilotConfig(
            drone_id=5,
            mavsdk_port=14560,
            mavlink_port=14550,
            mqtt_broker_address="mqtt.example.com:8883",
            sade_zone_config_path=None,
            custom_settings={"param1": "value1"},
        )
        assert config.drone_id == 5
        assert config.mavsdk_port == 14560
        assert config.mavlink_port == 14550
        assert config.mqtt_broker_address == "mqtt.example.com:8883"
        assert config.custom_settings == {"param1": "value1"}

    def test_drone_id_required(self) -> None:
        """Test that drone_id is required."""
        with pytest.raises(ValidationError):
            PilotConfig()  # type: ignore

    def test_drone_id_non_negative(self) -> None:
        """Test that drone_id must be non-negative."""
        with pytest.raises(ValidationError) as exc_info:
            PilotConfig(drone_id=-1)
        assert "greater than -1" in str(exc_info.value).lower()


class TestPilotConfigPorts:
    """Test port validation."""

    def test_mavsdk_port_range(self) -> None:
        """Test that MAVSDK port must be in valid port range."""
        # Valid port
        config = PilotConfig(drone_id=0, mavsdk_port=30000)
        assert config.mavsdk_port == 30000

        # Port too low
        with pytest.raises(ValidationError):
            PilotConfig(drone_id=0, mavsdk_port=512)

        # Port too high
        with pytest.raises(ValidationError):
            PilotConfig(drone_id=0, mavsdk_port=70000)

    def test_mavlink_port_range(self) -> None:
        """Test that MAVLink port must be in valid port range."""
        # Valid port
        config = PilotConfig(drone_id=0, mavlink_port=20000)
        assert config.mavlink_port == 20000

        # Port too low
        with pytest.raises(ValidationError):
            PilotConfig(drone_id=0, mavlink_port=512)

        # Port too high
        with pytest.raises(ValidationError):
            PilotConfig(drone_id=0, mavlink_port=70000)


class TestPilotConfigPaths:
    """Test path validation."""

    def test_zone_config_path_exists(self, tmp_zone_config: Path) -> None:
        """Test that zone config path is validated if provided."""
        # Valid path
        config = PilotConfig(drone_id=0, sade_zone_config_path=tmp_zone_config)
        assert config.sade_zone_config_path == tmp_zone_config

    def test_zone_config_path_nonexistent(self) -> None:
        """Test that nonexistent zone config path raises error."""
        with pytest.raises(ValueError, match="not found"):
            PilotConfig(drone_id=0, sade_zone_config_path=Path("/nonexistent/path"))


class TestPilotConfigSerialization:
    """Test config serialization."""

    def test_model_dump(self) -> None:
        """Test model_dump() output."""
        config = PilotConfig(
            drone_id=1,
            mavsdk_port=14551,
            custom_settings={"key": "value"},
        )
        dump = config.model_dump()
        assert dump["drone_id"] == 1
        assert dump["mavsdk_port"] == 14551
        assert dump["custom_settings"] == {"key": "value"}

    def test_model_dump_json_custom(self) -> None:
        """Test model_dump_json_custom() for JSON serialization."""
        config = PilotConfig(
            drone_id=2,
            mqtt_broker_address="broker.example.com:1883",
            custom_settings={"grid_size": 100},
        )
        json_str = config.model_dump_json_custom()
        data = json.loads(json_str)
        assert data["drone_id"] == 2
        assert data["mqtt_broker_address"] == "broker.example.com:1883"
        assert data["custom_settings"]["grid_size"] == 100

    def test_from_dict(self) -> None:
        """Test creating config from dict."""
        data = {
            "drone_id": 3,
            "mavsdk_port": 14553,
            "custom_settings": {"speed": 12},
        }
        config = PilotConfig(**data)
        assert config.drone_id == 3
        assert config.mavsdk_port == 14553
        assert config.custom_settings["speed"] == 12


class TestPilotConfigDefaults:
    """Test default values."""

    def test_mqtt_broker_default(self) -> None:
        """Test default MQTT broker address."""
        config = PilotConfig(drone_id=0)
        assert config.mqtt_broker_address == "localhost:1883"

    def test_custom_settings_default_empty(self) -> None:
        """Test that custom_settings defaults to empty dict."""
        config = PilotConfig(drone_id=0)
        assert config.custom_settings == {}

    def test_zone_config_default_none(self) -> None:
        """Test that zone config defaults to None."""
        config = PilotConfig(drone_id=0)
        assert config.sade_zone_config_path is None


class TestPilotConfigBackwardCompatibility:
    """Test backward compatibility aliases."""

    def test_pilot_settings_alias(self) -> None:
        """Test that PilotSettings is an alias for PilotConfig."""
        from software_pilot.config import PilotSettings

        assert PilotSettings is PilotConfig
