"""Example: Simple Waypoint Mission

This example demonstrates basic waypoint-following mission:
- Take off to 50m
- Fly to 3 waypoints
- Return home
- Land
"""

import asyncio

from droneresponse_mathtools import Lla
from software_pilot.config import PilotConfig
from software_pilot.uav import NED
from software_pilot.uav import MissionStep
from software_pilot.uav import ResilientDrone


async def simple_mission(config: PilotConfig, drone: ResilientDrone) -> None:
    """Execute a simple waypoint mission."""

    # Connect to drone
    await drone.connect()
    await drone.wait_for_global_position_estimate()

    # Fetch home position
    lat, lon, alt = await drone.fetch_drone_position()
    home = Lla(lat=lat, lon=lon, altitude=alt)

    # Mission parameters
    altitude = 50  # meters
    speed = config.custom_settings.get("speed_mps", 15.0)
    click = 100  # 100m units

    # Define waypoints
    mission = [
        MissionStep(
            short_name="takeoff",
            description="Take off to 50m",
            ned=NED(north=0, east=0, down=-altitude),
            home_alt=home.altitude,
            speed=speed,
            home=home,
        ),
        MissionStep(
            short_name="north",
            description="Fly north 1 click",
            ned=NED(north=click, east=0, down=-altitude),
            home_alt=home.altitude,
            speed=speed,
            home=home,
        ),
        MissionStep(
            short_name="northeast",
            description="Fly northeast 1 click",
            ned=NED(north=click, east=click, down=-altitude),
            home_alt=home.altitude,
            speed=speed,
            home=home,
        ),
        MissionStep(
            short_name="east",
            description="Fly east 1 click",
            ned=NED(north=0, east=click * 2, down=-altitude),
            home_alt=home.altitude,
            speed=speed,
            home=home,
        ),
        MissionStep(
            short_name="home",
            description="Return to home",
            ned=NED(north=0, east=0, down=-altitude),
            home_alt=home.altitude,
            speed=speed,
            home=home,
        ),
    ]

    # Execute mission
    await drone.execute_mission(mission)

    # Land
    await drone.action_land()


if __name__ == "__main__":
    import sys

    # For testing: create a mock config and drone
    config = PilotConfig(drone_id=0, mavsdk_port=14550)
    drone = ResilientDrone(
        listen_port="14540",
        drone_id=config.drone_id,
        mavsdk_port=config.mavsdk_port,
    )

    try:
        asyncio.run(simple_mission(config, drone))
    except KeyboardInterrupt:
        print("Mission cancelled")
        sys.exit(1)
