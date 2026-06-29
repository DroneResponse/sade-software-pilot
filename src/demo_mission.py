"""Demo mission for SADE drones."""

import asyncio
from typing import Any

from droneresponse_mathtools import Lla
from loguru import logger as log
from rich.traceback import install

from .cli_config import parse_args_from_cli
from .parameters_parser import FlightPath, get_params_based_on_fcu_id, parse_flight_path
from .uav import NED, LatLongAlt, MissionStep, ResilientDrone

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


async def create_mission(
    drone: ResilientDrone,
    home: Lla,
) -> None:
    log.info("Creating mission")

    # local vars
    speed_mps = 20.0
    cruising_altitude = 50
    speed_mps = 20.0
    startup_wait = 5

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

    for step in drone_flight_path.flight_path:
        if step.lat is None and step.lon is None:
            mission_step = MissionStep(
                short_name="takeoff",
                description="Take off from home position",
                ned=NED(north=0, east=0, down=-step.alt),
                home_alt=home.altitude,
                speed=speed_mps,
                home=home,
                move_lla=None,
            )
        else:
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
    listen_port: int,
    mavsdk_port: int,
    drone_id: int = 1,
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
    after_takeoff_delay_sec = 1
    await asyncio.sleep(after_takeoff_delay_sec)

    # start coroutine to print position every N seconds
    should_log_position_periodically = False
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

    await create_mission(
        drone=drone,
        home=home,
    )
    await drone.action_land()

    if cancel_position_task:
        cancel_position_task.set()
        if position_task:
            await position_task  # wait for the task to finish


async def main() -> None:
    """Mission entry point."""

    config = parse_args_from_cli()
    listen_port = config.listen_port
    drone_id = config.drone_id
    mavsdk_port = config.mavsdk_port
    param_files_path = config.param_files_path

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
