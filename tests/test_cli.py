"""Tests for software_pilot.cli module."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from software_pilot import cli


class TestParseArgs:
    """Test command-line argument parsing."""

    def test_required_drone_id(self) -> None:
        """Test that --drone-id is required."""
        with patch.object(sys, "argv", ["software-pilot"]):
            with pytest.raises(SystemExit):
                cli.parse_args()

    def test_drone_id_parsing(self) -> None:
        """Test parsing drone ID argument."""
        with patch.object(sys, "argv", ["software-pilot", "--drone-id=5"]):
            args = cli.parse_args()
            assert args.drone_id == 5

    def test_mavsdk_port_parsing(self) -> None:
        """Test parsing MAVSDK port argument."""
        with patch.object(
            sys, "argv", ["software-pilot", "--drone-id=0", "--mavsdk-port=14560"]
        ):
            args = cli.parse_args()
            assert args.mavsdk_port == 14560

    def test_mavlink_port_parsing(self) -> None:
        """Test parsing MAVLink port argument."""
        with patch.object(
            sys, "argv", ["software-pilot", "--drone-id=0", "--mavlink-port=14541"]
        ):
            args = cli.parse_args()
            assert args.mavlink_port == 14541

    def test_mqtt_broker_parsing(self) -> None:
        """Test parsing MQTT broker argument."""
        with patch.object(
            sys,
            "argv",
            ["software-pilot", "--drone-id=0", "--mqtt-broker=mqtt.example.com:8883"],
        ):
            args = cli.parse_args()
            assert args.mqtt_broker == "mqtt.example.com:8883"

    def test_mqtt_broker_default(self) -> None:
        """Test default MQTT broker value."""
        with patch.object(sys, "argv", ["software-pilot", "--drone-id=0"]):
            args = cli.parse_args()
            assert args.mqtt_broker == "localhost:1883"

    def test_sade_zone_config_parsing(self) -> None:
        """Test parsing SADE zone config path."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            zone_path = Path(f.name)

        try:
            with patch.object(
                sys,
                "argv",
                ["software-pilot", "--drone-id=0", f"--sade-zone-config={zone_path}"],
            ):
                args = cli.parse_args()
                assert args.sade_zone_config == zone_path
        finally:
            zone_path.unlink()

    def test_custom_config_parsing(self) -> None:
        """Test parsing custom config path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"key": "value"}, f)
            config_path = Path(f.name)

        try:
            with patch.object(
                sys,
                "argv",
                ["software-pilot", "--drone-id=0", f"--custom-config={config_path}"],
            ):
                args = cli.parse_args()
                assert args.custom_config == config_path
        finally:
            config_path.unlink()

    def test_loglevel_parsing(self) -> None:
        """Test parsing log level argument."""
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            with patch.object(
                sys, "argv", ["software-pilot", "--drone-id=0", f"--loglevel={level}"]
            ):
                args = cli.parse_args()
                assert args.loglevel == level

    def test_loglevel_default(self) -> None:
        """Test default log level."""
        with patch.object(sys, "argv", ["software-pilot", "--drone-id=0"]):
            args = cli.parse_args()
            assert args.loglevel == "INFO"

    def test_version_flag(self) -> None:
        """Test that --version flag works."""
        with patch.object(sys, "argv", ["software-pilot", "--version"]):
            with pytest.raises(SystemExit) as exc_info:
                cli.parse_args()
            assert exc_info.value.code == 0


class TestMain:
    """Test main() entry point."""

    def test_main_basic(self) -> None:
        """Test main() with basic arguments."""
        with patch.object(sys, "argv", ["software-pilot", "--drone-id=0"]):
            exit_code = cli.main()
            assert exit_code == 0

    def test_main_with_all_args(self) -> None:
        """Test main() with all arguments."""
        with patch.object(
            sys,
            "argv",
            [
                "software-pilot",
                "--drone-id=1",
                "--mavsdk-port=14551",
                "--mavlink-port=14541",
                "--mqtt-broker=mqtt.test.com:1883",
            ],
        ):
            exit_code = cli.main()
            assert exit_code == 0

    @pytest.mark.skip(reason="the do-nothing software pilot doesn't access any config")
    def test_main_missing_custom_config(self) -> None:
        """Test main() fails gracefully when custom config doesn't exist."""
        with patch.object(
            sys,
            "argv",
            [
                "software-pilot",
                "--drone-id=0",
                "--custom-config=/nonexistent/path.json",
            ],
        ):
            exit_code = cli.main()
            assert exit_code == 1

    @pytest.mark.skip(reason="the do-nothing software pilot doesn't access any config")
    def test_main_with_valid_custom_config(self) -> None:
        """Test main() with valid custom config file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"search_grid_size": 100}, f)
            config_path = Path(f.name)

        try:
            with patch.object(
                sys,
                "argv",
                ["software-pilot", "--drone-id=0", f"--custom-config={config_path}"],
            ):
                exit_code = cli.main()
                assert exit_code == 0
        finally:
            config_path.unlink()

    @pytest.mark.skip(
        reason="the do-nothing software pilot doesn't do anything and this test won't trigger the expected exception"
    )
    def test_main_exception_handling(self) -> None:
        """Test main() handles exceptions gracefully."""
        # Invalid drone_id type will be caught by argparse, but let's test value errors
        with patch.object(sys, "argv", ["software-pilot", "--drone-id=0"]):
            exit_code = cli.main()
            assert exit_code == 0
