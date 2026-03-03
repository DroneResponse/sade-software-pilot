import asyncio
import fcntl
import json
import math
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import Self

from loguru import logger as log
from pydantic import BaseModel
from pydantic import Field

from .config import ALLOWED_DRONE_IDS
from .config import LEASE_TIME
from .config import SADE_ZONE_CONFIG_FILE
from .config import SADE_ZONE_LEASE_FILE
from .config import SURVELLIANCE_DRONE_IDS_MAX
from .config import ZONE_THRESHOLD_METERS

LINE_POSSIBLE_WITH_POINTS = 2


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
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(**data)


class ZoneVerticeCoordinatesModel(BaseModel):
    """holds one of the vertices of sade zone"""

    latitude: float = Field(...)
    longitude: float = Field(...)


class SadeZone(BaseModel):
    """Holds all the vertices of a sade zone as per
    defination of the sade zone config file of Unreal Engine"""

    sade_id: str = Field(...)
    sade_name: str = Field(...)
    altitude: float = Field(..., gt=0)
    vertices: list[ZoneVerticeCoordinatesModel] = Field(...)

    def is_inside(
        self, latitude: float, longitude: float, altitude: float | None = None
    ) -> bool:
        """
        Check if a point (latitude, longitude, altitude) is inside the zone.
        Uses ray-casting algorithm for 2D polygon containment.

        Args:
            latitude: The latitude of the point
            longitude: The longitude of the point
            altitude: Optional altitude of the point. If provided,
                        checks if within zone altitude.

        Returns:
            True if the point is inside the zone, False otherwise
        """
        # If altitude is provided, check if it's within the zone's altitude
        # Assuming altitude defines the maximum height of the zone
        # (from ground/0 to altitude)
        if altitude is not None:
            if altitude < 0 or altitude > self.altitude:
                return False

        # Check if point is inside the polygon formed by
        # vertices using ray-casting algorithm
        compulsory_vertices = 3
        n = len(self.vertices)
        if n < compulsory_vertices:
            return False  # Need at least 3 vertices to form a polygon

        inside = False
        p1 = self.vertices[0]

        for i in range(1, n + 1):
            p2 = self.vertices[i % n]

            # Check if point is on the same latitude range as the edge
            if latitude > min(p1.latitude, p2.latitude):
                if latitude <= max(p1.latitude, p2.latitude):
                    if longitude <= max(p1.longitude, p2.longitude):
                        # Calculate intersection
                        if p1.latitude != p2.latitude:
                            x_intersection = (latitude - p1.latitude) * (
                                p2.longitude - p1.longitude
                            ) / (p2.latitude - p1.latitude) + p1.longitude
                            if (
                                p1.longitude == p2.longitude
                                or longitude <= x_intersection
                            ):
                                inside = not inside
            p1 = p2

        return inside

    def get_min_distance_from_zone(
        self,
        latitude: float,
        longitude: float,
        altitude: float,
    ) -> tuple[bool, float]:
        """
        Check if a point is near the zone boundary.
        """
        # First check if already inside the zone
        inside_res = self.is_inside(latitude, longitude, altitude)
        min_distance = float("inf")
        if not inside_res:
            # Check if nearby the zone boundary
            min_distance = self._min_distance_to_boundary(latitude, longitude)
        return inside_res, min_distance

    def _min_distance_to_boundary(self, latitude: float, longitude: float) -> float:
        """
        Calculate the minimum distance from a point
        to the zone boundary (polygon edges).

        Args:
            latitude: Point latitude
            longitude: Point longitude

        Returns:
            Minimum distance to boundary in meters
        """
        n = len(self.vertices)
        if n < LINE_POSSIBLE_WITH_POINTS:
            return float("inf")

        min_distance = float("inf")

        # Calculate distance to each edge of the polygon
        for i in range(n):
            p1 = self.vertices[i]
            p2 = self.vertices[(i + 1) % n]

            distance = self._distance_to_line_segment(
                latitude,
                longitude,
                p1.latitude,
                p1.longitude,
                p2.latitude,
                p2.longitude,
            )
            min_distance = min(min_distance, distance)

        return min_distance

    def _distance_to_line_segment(
        self,
        px: float,
        py: float,  # point coordinates (lat, lon)
        x1: float,
        y1: float,  # line segment start (lat, lon)
        x2: float,
        y2: float,  # line segment end (lat, lon)
    ) -> float:
        """
        Calculate the shortest distance from a point to a line segment.
        Uses approximation for small distances where lat/lon can be treated as planar.

        Args:
            px, py: Point coordinates (latitude, longitude)
            x1, y1: Line segment start (latitude, longitude)
            x2, y2: Line segment end (latitude, longitude)

        Returns:
            Distance in meters
        """
        # For better accuracy with lat/lon, convert to meters
        # using approximate conversion
        # At the equator: 1 degree lat ≈ 111,000 m,
        # 1 degree lon ≈ 111,000 * cos(lat) m
        avg_lat = (x1 + x2 + px) / 3
        lat_to_meters = 111000
        lon_to_meters = 111000 * math.cos(math.radians(avg_lat))

        # Convert to local meter coordinates
        px_m = px * lat_to_meters
        py_m = py * lon_to_meters
        x1_m = x1 * lat_to_meters
        y1_m = y1 * lon_to_meters
        x2_m = x2 * lat_to_meters
        y2_m = y2 * lon_to_meters

        # Calculate line segment length squared
        segment_length_sq = (x2_m - x1_m) ** 2 + (y2_m - y1_m) ** 2

        if segment_length_sq == 0:
            # Segment is a point, return distance to that point
            return math.sqrt((px_m - x1_m) ** 2 + (py_m - y1_m) ** 2)

        # Calculate projection of point onto line segment (parameterized by t)
        t = max(
            0,
            min(
                1,
                ((px_m - x1_m) * (x2_m - x1_m) + (py_m - y1_m) * (y2_m - y1_m))
                / segment_length_sq,
            ),
        )

        # Find closest point on segment
        closest_x = x1_m + t * (x2_m - x1_m)
        closest_y = y1_m + t * (y2_m - y1_m)

        # Return distance to closest point
        return math.sqrt((px_m - closest_x) ** 2 + (py_m - closest_y) ** 2)

    def get_sade_zone(self, zone_id: str | None) -> Self | None:
        if zone_id is None:
            return None
        if self.sade_id == zone_id:
            return self
        return None


class SadeZones:
    """Holds all the sade zones as per
    defination of the sade zone config file of Unreal Engine"""

    def __init__(self):
        self.zones: list[SadeZone] = self.load()
        self.drones: list[str] = []

    def get_sade_zone(self, zone_id: str) -> SadeZone | None:
        for zone in self.zones:
            if zone.get_sade_zone(zone_id):
                return zone
        return None

    @staticmethod
    def load(file_path: Path = SADE_ZONE_CONFIG_FILE) -> list[SadeZone]:
        res_zones: list[SadeZone] = []
        with file_path.open("r") as f:
            config_data: dict[str, Any] = json.loads(f.read())
            _zones = config_data.get("sade_zones", {})
            for zone in _zones:
                # here zone is the zone id that is key
                temp_zone = _zones.get(zone, None)
                if temp_zone:
                    vertices: list[ZoneVerticeCoordinatesModel] = [
                        ZoneVerticeCoordinatesModel(
                            latitude=vertice.get("latitude", 0),
                            longitude=vertice.get("longitude", 0),
                        )
                        for vertice in temp_zone.get("vertices", [])
                    ]
                    temp_zone_class = SadeZone(
                        sade_id=temp_zone.get("sade_id", ""),
                        sade_name=temp_zone.get("sade_name", ""),
                        altitude=temp_zone.get("altitude", 0),
                        vertices=vertices,
                    )
                    res_zones.append(temp_zone_class)
        return res_zones

    def classify_point_inside_zone(
        self, latitude: float, longitude: float, altitude: float, drone_id: int
    ) -> tuple[str | None, dict[str, float] | float]:
        nearby_zones = {}
        for zone in self.zones:
            inside, min_distance = zone.get_min_distance_from_zone(
                latitude, longitude, altitude
            )
            if inside:
                return zone.sade_id, min_distance
            if min_distance < ZONE_THRESHOLD_METERS and drone_id not in self.drones:
                nearby_zones[zone.sade_id] = min_distance
        return None, nearby_zones

    async def request_sade_zone_entry(
        self,
        drone,
        zone_sade_id: str,
        *,
        emulate_wait: bool = False,
    ) -> SadeZoneLease | None:
        """Atomically simulates a request for SADE Zone access."""
        if drone.drone_id in self.drones:
            # already present leased so ignore it
            return None
        drone.log("Pausing mission and holding position...")
        await drone.hold()

        if not SADE_ZONE_LEASE_FILE.exists():
            SADE_ZONE_LEASE_FILE.parent.mkdir(parents=True, exist_ok=True)
            SADE_ZONE_LEASE_FILE.write_text(json.dumps({}, default=str))

        # atomic file lock for concurrent lease updates
        with SADE_ZONE_LEASE_FILE.open("a+") as fp:
            # Try to acquire lock with timeout using non-blocking mode
            lock_acquired = False
            max_attempts = 50  # Try for ~5 seconds

            for _ in range(max_attempts):
                try:
                    # Use LOCK_NB for non-blocking lock attempt
                    fcntl.flock(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    lock_acquired = True
                    break
                except BlockingIOError:
                    # Lock is held by another process, wait a bit
                    await asyncio.sleep(0.1)

            if not lock_acquired:
                drone.log("Could not acquire lock after timeout")
                await drone.mission.start_mission()
                return None

            try:
                fp.seek(0)
                content = fp.read()
                zone_status = json.loads(content) if content else {}

                leases = [
                    SadeZoneLease.from_dict(lease_dict)
                    for lease_dict in zone_status.get("leases", [])
                ]
                active_leases = [
                    lease for lease in leases if lease.is_active(datetime.now(tz=UTC))
                ]
                # ruff: noqa: F841 - Not used for cryptographic purposes
                drones_in_zone = [lease.drone_id for lease in active_leases]

                if drone.drone_id in ALLOWED_DRONE_IDS:
                    now = datetime.now(tz=UTC)
                    expires_at = now + LEASE_TIME
                    lease = SadeZoneLease(
                        drone_id=drone.drone_id,
                        zone_id=zone_sade_id,
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
                    self.drones.append(drone.drone_id)

                    drone.log("SADE Zone leasing completed now drone is ready to fly")
                    drone.log("drone is now ready to fly")
                    return lease
                if (
                    drone.drone_id <= SURVELLIANCE_DRONE_IDS_MAX
                    and drone.drone_id not in ALLOWED_DRONE_IDS
                ):
                    drone.log("Drone ID not allowed let make them hold for monitoring")
                    return None
                # ruff: noqa: TRY300 - no check needed
                drone.set_set_home(True)
                self.drones.append(drone.drone_id)
                drone.log("Drone not allowed go home")
                return None

            except json.JSONDecodeError as err:
                log.error(f"Failed to decode JSON: {err}")
                return None
            finally:
                fcntl.flock(fp, fcntl.LOCK_UN)
