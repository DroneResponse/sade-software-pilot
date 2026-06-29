import argparse
from pathlib import Path

from pydantic import BaseModel


class CliConfig(BaseModel):
    listen_port: int
    drone_id: int
    mavsdk_port: int
    param_files_path: Path


def parse_args_from_cli() -> CliConfig:
    parser = argparse.ArgumentParser(description="Run a drone mission with MAVSDK")
    parser.add_argument(
        "--port",
        type=int,
        required=True,
        help="The UDP port on which to listen for incoming mavlink data.",
    )
    parser.add_argument(
        "--mavsdk-port",
        type=int,
        required=True,
        help="Each instance of mavsdk needs its own unique private port for internal use.",
    )
    parser.add_argument("--drone_id", type=int, required=True, help="Drone ID (0 or 1)")
    parser.add_argument(
        "--params-file", type=Path, required=True, help="Path to the parameters file"
    )

    args = parser.parse_args()
    return CliConfig(
        listen_port=args.port,
        drone_id=args.drone_id,
        mavsdk_port=args.mavsdk_port,
        param_files_path=args.params_file,
    )
