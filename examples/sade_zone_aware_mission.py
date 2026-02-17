"""Example: SADE Zone-Aware Mission

This example demonstrates:
- Requesting SADE zone access before entering airspace
- Handling zone access denial
- Dynamic behavior based on zone access
"""

import asyncio

from droneresponse_mathtools import Lla
from loguru import logger as log
from software_pilot.config import PilotConfig
from software_pilot.uav import NED
from software_pilot.uav import MissionStep
from software_pilot.uav import ResilientDrone
from software_pilot.zones import request_sade_zone_entry


async def zone_aware_mission(config: PilotConfig, drone: ResilientDrone) -> None:
    """Execute a mission that respects SADE zone access."""

    # Connect
    await drone.connect()
    await drone.wait_for_global_position_estimate()

    # Get home position
    lat, lon, alt = await drone.fetch_drone_position()
    home = Lla(lat=lat, lon=lon, altitude=alt)

    altitude = 50
    speed = config.custom_settings.get("speed_mps", 15.0)

    # Mission outside zone (always allowed)
    pre_zone_mission = [
        MissionStep(
            short_name="takeoff",
            description="Take off",
            ned=NED(north=0, east=0, down=-altitude),
            home_alt=home.altitude,
            speed=speed,
            home=home,
        ),
        MissionStep(
            short_name="approach_zone",
            description="Fly towards zone boundary",
            ned=NED(north=100, east=0, down=-altitude),
            home_alt=home.altitude,
            speed=speed,
            home=home,
        ),
    ]

    # Execute approach
    await drone.execute_mission(pre_zone_mission)

    # Request zone access
    log.info(f"Drone {config.drone_id} requesting SADE zone access")
    lease = request_sade_zone_entry(drone, emulate_wait=False)

    if lease:
        log.info(f"Zone access granted until {lease.expiration_time}")

        # Mission inside zone (approved)
        zone_mission = [
            MissionStep(
                short_name="enter_zone",
                description="Enter authorized zone",
                ned=NED(north=200, east=0, down=-altitude),
                home_alt=home.altitude,
                speed=speed,
                home=home,
            ),
            MissionStep(
                short_name="search_zone",
                description="Search within zone",
                ned=NED(north=300, east=100, down=-altitude),
                home_alt=home.altitude,
                speed=speed,
                home=home,
            ),
            MissionStep(
                short_name="exit_zone",
                description="Exit zone before lease expires",
                ned=NED(north=100, east=0, down=-altitude),
                home_alt=home.altitude,
                speed=speed,
                home=home,
            ),
        ]

        await drone.execute_mission(zone_mission)

    else:
        log.warning(f"Drone {config.drone_id} denied zone access")

        # Return home if denied (optional)
        return_mission = [
            MissionStep(
                short_name="return_home",
                description="Return to home due to zone denial",
                ned=NED(north=0, east=0, down=-altitude),
                home_alt=home.altitude,
                speed=speed,
                home=home,
            ),
        ]

        await drone.execute_mission(return_mission)

    # Land
    await drone.action_land()


if __name__ == "__main__":
    import sys

    config = PilotConfig(drone_id=0, mavsdk_port=14550)
    drone = ResilientDrone(
        listen_port="14540",
        drone_id=config.drone_id,
        mavsdk_port=config.mavsdk_port,
    )

    try:
        asyncio.run(zone_aware_mission(config, drone))
    except KeyboardInterrupt:
        print("Mission cancelled")
        sys.exit(1)
