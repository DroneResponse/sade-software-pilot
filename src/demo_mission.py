"""Demo mission for SADE drones."""

import argparse
import asyncio
import random

from droneresponse_mathtools import Lla
from loguru import logger as log
from rich.traceback import install

from .uav import NED
from .uav import MissionStep
from .uav import ResilientDrone

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
    if drone.drone_id > 15:
        cruising_altitude = 30
    else:
        cruising_altitude = 70
    clicks = 40  # defining click as 100m;
    speed_mps = 20.0

    take_off = [
        MissionStep(
            short_name="takeoff",
            description="Take off from home position",
            ned=NED(north=0, east=0, down=-cruising_altitude),
            home_alt=home.altitude,
            speed=speed_mps,
            home=home,
        )
    ]

    random_mission = [
        MissionStep(
            short_name="go_north",
            description="Going 2 clicks north",
            ned=NED(north=2 * clicks, east=0, down=-cruising_altitude),
            home_alt=home.altitude,
            speed=speed_mps,
            home=home,
        ),
        MissionStep(
            short_name="go_east",
            description="Going 2 clicks east",
            ned=NED(north=0, east=2 * clicks, down=-cruising_altitude),
            home_alt=home.altitude,
            speed=speed_mps,
            home=home,
        ),
        MissionStep(
            short_name="go_west",
            description="Going 2 clicks west",
            ned=NED(north=0, east=-2 * clicks, down=-cruising_altitude),
            home_alt=home.altitude,
            speed=speed_mps,
            home=home,
        ),
        # Northwest
        MissionStep(
            short_name="go_northwest",
            description="Going 2 clicks northwest",
            ned=NED(north=2 * clicks, east=-2 * clicks, down=-cruising_altitude),
            home_alt=home.altitude,
            speed=speed_mps,
            home=home,
        ),
    ]

    return_to_base_home = [
        MissionStep(
            short_name="return_to_base",
            description="SADE Zone access denied; Returning home",
            ned=NED(north=0, east=0, down=-cruising_altitude),
            home_alt=home.altitude,
            speed=speed_mps,
            home=home,
        ),
    ]

    drone.set_home_mission(return_to_base_home)

    log.info("Drone is starting the mission, taking off!!")
    await asyncio.sleep(1)
    await drone.execute_mission(mission_steps=take_off)
    while not drone.get_set_home():
        await asyncio.sleep(1)
        # ruff: noqa: S311 - Not used for cryptographic purposes
        choiced_mission = random.choices(random_mission, k=3)
        await drone.execute_mission(mission_steps=choiced_mission)
    drone.set_set_home(False)
    await drone.execute_mission(mission_steps=return_to_base_home)


async def run(listen_port: str, mavsdk_port: int, drone_id: int = 0) -> None:
    """Main entry point for the mission."""
    drone = ResilientDrone(
        listen_port=listen_port, drone_id=drone_id, mavsdk_port=mavsdk_port
    )
    await drone.connect()

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


def main() -> None:
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

    args = parser.parse_args()

    listen_port = args.port
    drone_id = args.drone_id
    mavsdk_port = args.mavsdk_port

    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        run(listen_port=listen_port, drone_id=drone_id, mavsdk_port=mavsdk_port)
    )

    log.info(f"All missions completed for drone {drone_id}")


if __name__ == "__main__":
    main()
