"""Command-line interface for the software pilot."""

import argparse
import json
import sys
from pathlib import Path

from loguru import logger as log

from . import __version__
from .config import PilotConfig


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="SADE Software Pilot: Autonomous drone mission executor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  software-pilot --drone-id=0 --mavsdk-port=14550
  software-pilot --drone-id=1 --custom-config=/etc/pilot/drone1.json
""",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    parser.add_argument(
        "--drone-id",
        type=int,
        required=True,
        help="Unique drone identifier (0-based index)",
    )

    parser.add_argument(
        "--mavsdk-port",
        type=int,
        default=14550,
        help="gRPC port for MAVSDK autopilot communication (default: 14550)",
    )

    parser.add_argument(
        "--mavlink-port",
        type=int,
        default=14540,
        help="UDP port for MAVLink protocol (default: 14540)",
    )

    parser.add_argument(
        "--mqtt-broker",
        default="localhost:1883",
        help="MQTT broker address host:port (default: localhost:1883)",
    )

    parser.add_argument(
        "--sade-zone-config",
        type=Path,
        help="Path to SADE zone configuration JSON file",
    )

    parser.add_argument(
        "--custom-config",
        type=Path,
        help="Path to custom mission configuration JSON file",
    )

    parser.add_argument(
        "--loglevel",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point for the software pilot CLI."""
    args = parse_args()

    # Configure logging
    log.remove()  # Remove default handler
    log.add(
        sys.stderr,
        level=args.loglevel,
        format="<level>{level: <8}</level> | {time:YYYY-MM-DD HH:mm:ss} | {name}:{function}:{line} - {message}",
    )

    try:
        # Build config from CLI args
        config_dict = {
            "drone_id": args.drone_id,
            "mavsdk_port": args.mavsdk_port,
            "mavlink_port": args.mavlink_port,
            "mqtt_broker_address": args.mqtt_broker,
            "sade_zone_config_path": args.sade_zone_config,
        }

        # Load custom settings if provided
        if args.custom_config:
            if not args.custom_config.exists():
                log.error(f"Custom config file not found: {args.custom_config}")
                return 1
            with open(args.custom_config) as f:
                custom = json.load(f)
            config_dict["custom_settings"] = custom
            log.info(f"Loaded custom configuration from {args.custom_config}")

        # Validate and create config
        config = PilotConfig(**config_dict)
        log.info(
            f"Software Pilot v{__version__} initialized for drone {config.drone_id}"
        )
        log.debug(f"Configuration: {config}")

        # Run the mission (placeholder for now)
        # In the future, this will call the actual mission logic
        log.info("Mission execution placeholder - implement actual mission logic")

        return 0

    except ValueError as e:
        log.error(f"Configuration error: {e}")
        return 1
    except Exception as e:
        log.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
