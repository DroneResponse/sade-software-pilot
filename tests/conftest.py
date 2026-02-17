"""Shared test fixtures and configuration."""

import json
import tempfile
from pathlib import Path

import pytest
from software_pilot.config import PilotConfig


@pytest.fixture
def tmp_config_file() -> Path:
    """Create a temporary config file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        config = {
            "search_grid_size": 100,
            "speed_mps": 15,
            "loiter_radius": 50,
        }
        json.dump(config, f)
        path = Path(f.name)
    yield path
    path.unlink()


@pytest.fixture
def tmp_zone_config() -> Path:
    """Create a temporary zone config file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        zone_config = {
            "zones": [
                {
                    "id": "sade-zone-1",
                    "center": {"lat": 41.6, "lon": -86.35},
                    "radius_m": 5000,
                }
            ]
        }
        json.dump(zone_config, f)
        path = Path(f.name)
    yield path
    path.unlink()


@pytest.fixture
def basic_pilot_config() -> PilotConfig:
    """Create a basic PilotConfig for testing."""
    return PilotConfig(
        drone_id=0,
        mavsdk_port=14550,
        mavlink_port=14540,
        mqtt_broker_address="localhost:1883",
        sade_zone_config_path=None,
        custom_settings={},
    )


@pytest.fixture
def pilot_config_with_settings(tmp_config_file: Path) -> PilotConfig:
    """Create a PilotConfig with custom settings."""
    return PilotConfig(
        drone_id=1,
        mavsdk_port=14551,
        mavlink_port=14541,
        mqtt_broker_address="mqtt.example.com:1883",
        sade_zone_config_path=None,
        custom_settings={"search_grid_size": 100, "speed_mps": 15},
    )


@pytest.fixture
def pilot_config_with_zones(tmp_zone_config: Path) -> PilotConfig:
    """Create a PilotConfig with zone configuration."""
    return PilotConfig(
        drone_id=2,
        mavsdk_port=14552,
        mavlink_port=14542,
        mqtt_broker_address="localhost:1883",
        sade_zone_config_path=tmp_zone_config,
        custom_settings={},
    )
