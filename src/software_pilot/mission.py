"""Example autonomous drone mission for SADE simulations."""

import asyncio

from droneresponse_mathtools import Lla
from loguru import logger as log

from .config import PilotConfig
from .uav import NED
from .uav import MissionStep
from .uav import ResilientDrone
from .zones import request_sade_zone_entry


async def run_example_mission(config: PilotConfig, drone: ResilientDrone) -> None:
    """Execute an example mission that includes SADE zone requests.

    Args:
        config: Pilot configuration
        drone: Connected ResilientDrone instance
    """
    log.info(f"Starting example mission for drone {config.drone_id}")

    try:
        # Fetch initial position
        lat, lon, alt = await drone.fetch_drone_position()
        home = Lla(lat=lat, lon=lon, altitude=alt)
        log.info(f"Home position: {home}")

        # Create simple mission with SADE zone awareness
        mission = await create_example_mission(home)

        # Upload and execute
        await drone.execute_mission(mission)

        # Check  for SADE zone access if within proximity
        cancel_event = asyncio.Event()
        monitoring_task = asyncio.create_task(
            monitor_sade_zones(drone, home, cancel_event)
        )

        # Wait for mission to complete
        await asyncio.sleep(2)  # Simple wait; in practice, hook to mission completion

        # Cleanup
        cancel_event.set()
        await monitoring_task

        # Land
        await drone.action_land()
        log.info("Mission completed successfully")

    except Exception as e:
        log.exception(f"Mission execution failed: {e}")
        raise


async def create_example_mission(home: Lla) -> list[MissionStep]:
    """Create an example waypoint mission.

    Args:
        home: Home location (Lla object)

    Returns:
        List of MissionStep objects
    """
    speed_mps = 20.0
    cruising_altitude = 50.0
    click = 100  # 100 meters

    mission = [
        MissionStep(
            short_name="takeoff",
            description="Take off from home position",
            ned=NED(north=0, east=0, down=-cruising_altitude),
            home_alt=home.altitude,
            speed=speed_mps,
            home=home,
        ),
        MissionStep(
            short_name="waypoint_1",
            description="First waypoint: 1 click north",
            ned=NED(north=click, east=0, down=-cruising_altitude),
            home_alt=home.altitude,
            speed=speed_mps,
            home=home,
        ),
        MissionStep(
            short_name="waypoint_2",
            description="Second waypoint: 1 click east",
            ned=NED(north=click, east=click, down=-cruising_altitude),
            home_alt=home.altitude,
            speed=speed_mps,
            home=home,
        ),
        MissionStep(
            short_name="waypoint_3",
            description="Third waypoint: return to home (north offset)",
            ned=NED(north=0, east=0, down=-cruising_altitude),
            home_alt=home.altitude,
            speed=speed_mps,
            home=home,
        ),
    ]

    return mission


async def monitor_sade_zones(
    drone: ResilientDrone,
    home: Lla,
    cancel_event: asyncio.Event,
    check_interval_sec: int = 5,
) -> None:
    """Monitor drone position and request SADE zone access if needed.

    Args:
        drone: Connected ResilientDrone instance
        home: Home location reference
        cancel_event: Event to signal monitoring stop
        check_interval_sec: Interval between zone checks (seconds)
    """
    log.info("Starting SADE zone monitoring")

    # Example: define a SADE zone to request access for
    # In practice, this would load from config or flight plan
    sade_zone_request_enabled = False  # Disable for now to simplify

    while not cancel_event.is_set():
        try:
            if sade_zone_request_enabled:
                # Get current position
                lat, lon, alt = await drone.fetch_drone_position()

                # Check proximity to zone and request access if needed
                # (details omitted for brevity)
                lease = request_sade_zone_entry(drone, emulate_wait=False)
                if lease:
                    log.info(
                        f"SADE zone access granted: {lease.zone_id} "
                        f"(expires {lease.expiration_time})"
                    )

        except Exception as e:
            log.warning(f"SADE zone check failed: {e}")

        await asyncio.sleep(check_interval_sec)

    log.info("SADE zone monitoring stopped")
