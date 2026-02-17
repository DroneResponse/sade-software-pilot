import fcntl
import json
import time
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Any

from loguru import logger as log
from pydantic import BaseModel
from pydantic import Field

from .uav import ResilientDrone

MAX_DRONES_IN_ZONE = 1
LEASE_TIME = timedelta(minutes=5)
SADE_ZONE_LEASE_FILE = Path("/") / "tmp" / "run" / "control" / "sade_zone_leases.json"


class SadeZoneLease(BaseModel):
    """Represents a lease to operate in a SADE Zone."""

    drone_id: int
    zone_id: str = Field(default="sade-zone-1")
    grant_time: datetime
    expiration_time: datetime

    def is_active(self, now: datetime) -> bool:
        return self.grant_time <= now < self.expiration_time

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SadeZoneLease":
        return cls(**data)


def request_sade_zone_entry(
    drone: ResilientDrone,
    *,
    emulate_wait: bool = False,
) -> SadeZoneLease | None:
    """Atomically simulates a request for SADE Zone access."""
    if emulate_wait:
        sade_zone_req_time = 5
        time.sleep(sade_zone_req_time * drone.drone_id)
    if not SADE_ZONE_LEASE_FILE.exists():
        SADE_ZONE_LEASE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SADE_ZONE_LEASE_FILE.write_text(json.dumps({}, default=str))

    # atomic file lock for concurrent lease updates
    # w+ mode might be unsafe for concurrent use.
    with SADE_ZONE_LEASE_FILE.open("a+") as fp:
        try:
            fcntl.flock(fp, fcntl.LOCK_EX)
        except OSError:
            log.info("Could not acquire lock")
        try:
            fp.seek(0)
            zone_status = json.load(fp)

            leases = [
                SadeZoneLease.from_dict(lease_dict)
                for lease_dict in zone_status.get("leases", [])
            ]
            active_leases = [
                lease for lease in leases if lease.is_active(datetime.now(tz=UTC))
            ]
            drones_in_zone = [lease.drone_id for lease in active_leases]

            if (
                len(drones_in_zone) < MAX_DRONES_IN_ZONE
                and drone.drone_id not in drones_in_zone
            ):
                now = datetime.now(tz=UTC)
                expires_at = now + LEASE_TIME
                lease = SadeZoneLease(
                    drone_id=drone.drone_id,
                    zone_id="sade-zone-1",
                    grant_time=now,
                    expiration_time=expires_at,
                )
                leases.append(lease)
                zone_status["leases"] = [lease.to_dict() for lease in leases]
                fp.seek(0)
                fp.truncate()
                json.dump(zone_status, fp, default=str)
                fp.flush()
                fcntl.flock(fp, fcntl.LOCK_UN)
                return lease
        except json.JSONDecodeError as err:
            log.error(f"Failed to decode JSON: {err}")
            return None
        finally:
            fcntl.flock(fp, fcntl.LOCK_UN)
    return None


def load_zone_status(path: Path) -> dict[str, Any]:
    if path.exists():
        with path.open("r") as f:
            return json.load(f)
    return {}


def save_zone_status(path: Path, status: dict[str, Any]) -> None:
    with path.open("w") as f:
        json.dump(status, f, default=str)
