import json
from datetime import timedelta
from pathlib import Path
from typing import Any
from pydantic import BaseModel

# Used for calcaulations
MAX_LAT = 90
MIN_LAT = -MAX_LAT
MAX_LON = 180
MIN_LON = -MAX_LON
MIN_SPEED = 0


# Sade Zone related configurations
MAX_DRONES_IN_ZONE = 1
ALLOWED_DRONE_IDS = [1, 2, 3, 4, 5]
SURVELLIANCE_DRONE_IDS_MAX = 15
LEASE_TIME = timedelta(minutes=5)
ZONE_THRESHOLD_METERS = 50  # this value is in meters
ZONE_REQUEST_THRESHOLD_METERS = 15  # this value is in meters

# File path configgurations for sade_zones
SADE_ZONE_LEASE_FILE = Path("/") / "tmp" / "run" / "control" / "sade_zone_leases.json"
SADE_ZONE_CONFIG_FILE = (
    Path("/") / "tmp" / "run" / "config" / "unreal" / "server_config.json"
)

class ActionsForFCU(BaseModel):
    short_name: str | None
    description: str | None
    lat: float | None
    lon: float | None
    alt: float | None
    home: bool


class FlightPath(BaseModel):
    drone_id: int
    flight_path: list[ActionsForFCU]

    def __repr__(self) -> str:
        return f"FlightPath(drone_id={self.drone_id}, flight_path's length ={len(self.flight_path)})"


def parse_flight_path() -> dict[str, FlightPath]:
    BASE_PATH = Path(__file__).parent
    flight_path = BASE_PATH / "flight_path.json"
    with open(flight_path, "r") as file_buffer:
        params = json.load(file_buffer)
    result = {}
    for item in params:
        result[item["drone_id"]] = FlightPath(**item)
    return result


def get_origin():
    with SADE_ZONE_CONFIG_FILE.open("r") as f:
        config_data: dict[str, Any] = json.loads(f.read())
        world = config_data.get("simulation_world", {})
        origin = world.get("origin", {})
        lat = origin.get("latitude", 0)
        lon = origin.get("longitude", 0)
        alt = origin.get("altitude", 0)
    return lat, lon, alt
