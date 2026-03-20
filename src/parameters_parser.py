"""
Parameter parsing module for the Sade Software Pilot.
"""

import json
from pathlib import Path
from typing import Any


def get_params_based_on_fcu_id(fcu_id: str, file_path: Path) -> dict[Any, Any]:
    file_path = file_path.resolve()
    params = {}
    with open(file_path, "r") as file_buffer:
        params = json.load(file_buffer)
    return params.get(fcu_id, {})
