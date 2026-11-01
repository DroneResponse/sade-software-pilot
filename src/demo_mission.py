"""Demo mission for SADE drones."""

import argparse
import asyncio
from pathlib import Path
from typing import Any

from droneresponse_mathtools import Lla
from loguru import logger as log
from rich.traceback import install

install(show_locals=True)

async def main() -> None:
    """Mission entry point."""
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
    drone_id = args.drone_id

    log.info("This Software Pilot doesnt do anything, Hook Dr_Onboard as software pilot instead!")
    log.info(f"Drone ID: {drone_id} is waiting for Dr_Onboard to issue commands!!")


if __name__ == "__main__":
    asyncio.run(main())
