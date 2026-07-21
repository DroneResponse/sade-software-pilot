"""Demo mission for SADE drones."""

import argparse
import asyncio
from pathlib import Path
from this import s
from typing import Any

from droneresponse_mathtools import Lla
from loguru import logger as log
from rich.traceback import install

from .parameters_parser import get_params_based_on_fcu_id
from .uav import NED
from .uav import MissionStep
from .uav import ResilientDrone, LatLongAlt
from .config import parse_flight_path, FlightPath

install(show_locals=True)


async def log_position_periodically(
    drone: ResilientDrone,
    cancel_event: asyncio.Event,
    delay_sec: int = 5,
) -> None:
    while not cancel_event.is_set():
        async for position in drone.telemetry_position():
            log.debug(
                f"Drone {drone.drone_id}: "
                f"lat {position.latitude_deg:.6f} "
                f"lon {position.longitude_deg:.6f}, "
                f"alt (rel) {position.relative_altitude_m:.6f}, "
                f"alt (abs) {position.absolute_altitude_m:.6f}"
            )
            break  # ensure we only take the latest position in each iteration
        await asyncio.sleep(delay_sec)


async def check_sade_zones_periodically(
    drone: ResilientDrone,
    cancel_event: asyncio.Event,
    delay_sec: int = 1,
) -> None:
    while not cancel_event.is_set():
        await drone.check_inside_sade_zones()
        await asyncio.sleep(delay_sec)


async def create_mission(
    drone: ResilientDrone,
    home: Lla,
) -> None:
    log.info("Creating mission")

    # local vars
    speed_mps = 20.0
    cruising_altitude = 50
    speed_mps = 20.0
    startup_wait = 2

    flight_path: dict[str, FlightPath] = parse_flight_path()
    drone_flight_path: FlightPath = flight_path[str(drone.drone_id)]

    # the "click" unit makes it easier to scale the mission up or down
    log.info(f"Drone flight path: {drone_flight_path}")

    _mission_script_return_to_base = [
        MissionStep(
            short_name="return_to_base",
            description="SADE Zone access denied; Returning home",
            ned=NED(north=0, east=0, down=-cruising_altitude),
            home_alt=home.altitude,
            speed=speed_mps,
            home=home,
            move_lla=None,
        ),
    ]

    _mission_scripts = []
    mission_step = None
    for step in drone_flight_path.flight_path:
        if step.lat is None and step.lon is None and step.alt is not None:
            mission_step = MissionStep(
                short_name="takeoff",
                description="Take off from home position",
                ned=NED(north=0, east=0, down=-step.alt),
                home_alt=home.altitude,
                speed=speed_mps,
                home=home,
                move_lla=None,
            )
        elif step.lat is not None and step.lon is not None and step.alt is not None:
            mission_step = MissionStep(
                short_name=step.short_name,
                description=step.description,
                ned=None,
                home_alt=home.altitude,
                speed=speed_mps,
                home=home,
                move_lla=LatLongAlt(
                    lat=step.lat, lon=step.lon, alt=step.alt + cruising_altitude
                ),
            )
        _mission_scripts.append(mission_step)

    sleep_time = startup_wait
    log.info(f"Drone {drone.drone_id} waiting {sleep_time} seconds before starting")
    await asyncio.sleep(sleep_time)

    try:
        await drone.execute_mission(mission_steps=_mission_scripts)
    except Exception as err:
        # always return to base
        log.error(err)
        await drone.execute_mission(mission_steps=_mission_script_return_to_base)
        raise


async def run(
    listen_port: str,
    mavsdk_port: int,
    drone_id: int = 0,
    params: dict[Any, Any] = {},
) -> None:
    """Main entry point for the mission."""
    drone = ResilientDrone(
        listen_port=listen_port, drone_id=drone_id, mavsdk_port=mavsdk_port
    )
    await drone.connect()

    log.info(f"The Drone ID is {drone_id},  is ingested with params {params}")

    log.info("Waiting for drone to have a global position estimate…")
    try:
        await asyncio.wait_for(drone.wait_for_global_position_estimate(), timeout=90.0)
    except TimeoutError:
        log.info("Timeout waiting for global position. Exiting…")
        return

    (
        current_latitude,
        current_longitude,
        current_altitude,
    ) = await drone.fetch_drone_position()

    home = Lla(
        latitude=current_latitude,
        longitude=current_longitude,
        altitude=current_altitude,
    )

    await drone.action_arm()
    await drone.action_takeoff()
    after_takeoff_delay_sec = 2
    await asyncio.sleep(after_takeoff_delay_sec)

    # start coroutine to print position every N seconds
    should_log_position_periodically = False
    should_drone_check_sade_zone_periodically = True
    cancel_sade_zone_task = None
    sade_zone_task = None
    cancel_position_task = None
    position_task = None

    if should_log_position_periodically:
        cancel_position_task = asyncio.Event()
        position_task = asyncio.create_task(
            log_position_periodically(
                drone=drone,
                cancel_event=cancel_position_task,  # signals task cancellation
                delay_sec=5,
            ),
        )

    if should_drone_check_sade_zone_periodically:
        cancel_sade_zone_task = asyncio.Event()
        sade_zone_task = asyncio.create_task(
            check_sade_zones_periodically(
                drone=drone,
                cancel_event=cancel_sade_zone_task,  # signals task cancellation
                delay_sec=1,
            ),
        )

    await create_mission(
        drone=drone,
        home=home,
    )
    await drone.action_land()

    if cancel_sade_zone_task:
        cancel_sade_zone_task.set()
        if sade_zone_task:
            await sade_zone_task  # wait for the task to finish

    if cancel_position_task:
        cancel_position_task.set()
        if position_task:
            await position_task  # wait for the task to finish


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
        help="Each instance of MAVSDK needs its own unique priv port for internal use.",
    )
    parser.add_argument("--drone_id", type=int, required=True, help="Drone ID (0 or 1)")
    parser.add_argument(
        "--params-file", type=Path, required=True, help="Path to the parameters file"
    )

    args = parser.parse_args()

    listen_port = args.port
    drone_id = args.drone_id
    mavsdk_port = args.mavsdk_port
    param_files_path = args.params_file

    params = get_params_based_on_fcu_id(drone_id, param_files_path)

    await run(
        listen_port=listen_port,
        drone_id=drone_id,
        mavsdk_port=mavsdk_port,
        params=params,
    )

    log.info(f"All missions completed for drone {drone_id}")


if __name__ == "__main__":
    asyncio.run(main())
