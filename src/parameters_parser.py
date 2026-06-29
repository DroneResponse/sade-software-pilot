"""
Parameter parsing module for the Sade Software Pilot.
"""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


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


def get_params_based_on_fcu_id(fcu_id: int, file_path: Path) -> dict[Any, Any]:
    file_path = file_path.resolve()
    params = {}
    with open(file_path, "r") as file_buffer:
        params = json.load(file_buffer)
    return params.get(f"{fcu_id}", params.get(fcu_id, {}))


def parse_flight_path() -> dict[str, FlightPath]:
    BASE_PATH = Path(__file__).parent
    flight_path = BASE_PATH / "flight_path.json"
    with open(flight_path, "r") as file_buffer:
        params = json.load(file_buffer)
    result = {}
    for item in params:
        result[item["drone_id"]] = FlightPath(**item)
    return result
