"""Demo mission for SADE drones."""

import argparse
import asyncio
from pathlib import Path
from typing import Any

from droneresponse_mathtools import Lla
from loguru import logger as log
from rich.traceback import install

from .parameters_parser import get_params_based_on_fcu_id
from .uav import NED
from .uav import MissionStep
from .uav import ResilientDrone
from .zones import SadeZoneLease
from .zones import request_sade_zone_entry

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
    clicks = 100  # defining click as 100m;
    speed_mps = 20.0
    startup_wait = 10

    # the "click" unit makes it easier to scale the mission up or down

    _mission_script_outsize_sz = [
        MissionStep(
            short_name="takeoff",
            description="Take off from home position",
            ned=NED(north=0, east=0, down=-cruising_altitude),
            home_alt=home.altitude,
            speed=speed_mps,
            home=home,
        ),
        MissionStep(
            short_name="request_sz",
            description="Go 1 click west and ask for SADE zone access",
            ned=NED(north=0, east=-1 * clicks, down=-cruising_altitude),
            home_alt=home.altitude,
            speed=speed_mps,
            home=home,
        ),
    ]

    _mission_script_sz_granted = [
        MissionStep(
            short_name="enter_sz",
            description="SADE Zone access granted; Going one more click west",
            ned=NED(north=0, east=-2 * clicks, down=-cruising_altitude),
            home_alt=home.altitude,
            speed=speed_mps,
            home=home,
        ),
        MissionStep(
            short_name="go_north",
            description="Go two clicks north",
            ned=NED(north=2 * clicks, east=-2 * clicks, down=-cruising_altitude),
            home_alt=home.altitude,
            speed=speed_mps,
            home=home,
        ),
        MissionStep(
            short_name="return",
            description="Returning to origin",
            ned=NED(north=0, east=0, down=-cruising_altitude),
            home_alt=home.altitude,
            speed=speed_mps,
            home=home,
        ),
    ]

    _mission_script_return_to_base = [
        MissionStep(
            short_name="return_to_base",
            description="SADE Zone access denied; Returning home",
            ned=NED(north=0, east=0, down=-cruising_altitude),
            home_alt=home.altitude,
            speed=speed_mps,
            home=home,
        ),
    ]

    _mission_script_sz_denied = _mission_script_return_to_base

    sleep_time = startup_wait * drone.drone_id + 60
    log.info(f"Drone {drone.drone_id} waiting {sleep_time} seconds before starting")
    await asyncio.sleep(sleep_time)
    await drone.execute_mission(mission_steps=_mission_script_outsize_sz)
    log.info("Waiting for SADE Zone access...")
    try:
        sade_zone_lease: SadeZoneLease | None = request_sade_zone_entry(
            drone=drone,
            emulate_wait=True,
        )
        if sade_zone_lease:
            drone.log(
                f"SADE Zone access granted until {sade_zone_lease.expiration_time}"
            )
            await drone.execute_mission(mission_steps=_mission_script_sz_granted)
        else:
            drone.log_warning("SADE Zone access denied; returning to base.")
            await drone.execute_mission(mission_steps=_mission_script_sz_denied)
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
    after_takeoff_delay_sec = 5
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
    return 0
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
