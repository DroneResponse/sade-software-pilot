"""Wrapper class for UAV."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from math import cos
from math import hypot
from math import isclose
from math import isfinite
from math import radians

import grpc
from droneresponse_mathtools import Lla
from loguru import logger as log
from mavsdk import System
from mavsdk.mission import Mission
from mavsdk.mission import MissionError
from mavsdk.mission import MissionItem
from mavsdk.mission import MissionPlan
from mavsdk.mission import MissionProgress

from .config import MAX_LAT
from .config import MAX_LON
from .config import MIN_LAT
from .config import MIN_LON
from .config import MIN_SPEED
from .config import ZONE_REQUEST_THRESHOLD_METERS
from .config import get_origin
from .zones import SadeZoneLease
from .zones import SadeZones

NEARBY_RECHECK_INTERVAL = 1
METERS_PER_DEGREE_LATITUDE = 111_000.0
GEOMETRY_EPSILON = 1e-7


@dataclass
class NED:
    """North-East-Down coordinates."""

    north: float
    east: float
    down: float

@dataclass
class LatLongAlt:
    """Latitude-Longitude-Altitude coordinates."""

    lat: float
    lon: float
    alt: float


@dataclass
class MissionStep:
    """Represents a single step in a waypoint-based mission."""

    short_name: str | None
    description: str | None
    ned: NED | None
    home_alt: float
    speed: float
    home: Lla
    move_lla: LatLongAlt | None = None

    def create_mission_item(self) -> MissionItem:
        """Creates a MissionItem based on the NED coordinates relative to home."""
        pos_lla: Lla | LatLongAlt = self.home
        if self.ned is None:
            pos_lla = self.move_lla
        else:
            pos_lla = self._create_lla_vector()
        log.trace(
            "Creating waypoint at "
            f"{pos_lla.lat:.6f}, {pos_lla.lon:.6f}, {pos_lla.alt:.2f}"
        )
        return _create_mission_item(
            lat=pos_lla.lat,
            lon=pos_lla.lon,
            alt=pos_lla.alt - self.home_alt,
            speed=self.speed,
        )

    def _create_lla_vector(self) -> Lla:
        if self.ned is None:
            return self.home
        result = self.home.move_ned(
            north=self.ned.north, east=self.ned.east, down=self.ned.down
        )
        if not isinstance(result, Lla):
            msg = "move_ned did not return Lla type"
            raise TypeError(msg)
        return result


def _horizontal_distance_m(
    latitude_1: float,
    longitude_1: float,
    latitude_2: float,
    longitude_2: float,
) -> float:
    """Calculate approximate horizontal distance for nearby coordinates."""
    reference_latitude = (latitude_1 + latitude_2) / 2.0
    longitude_scale = (
        METERS_PER_DEGREE_LATITUDE
        * cos(radians(reference_latitude))
    )

    north_m = (
        latitude_2 - latitude_1
    ) * METERS_PER_DEGREE_LATITUDE

    east_m = (
        longitude_2 - longitude_1
    ) * longitude_scale

    return hypot(east_m, north_m)


def _to_local_xy(
    latitude: float,
    longitude: float,
    reference_latitude: float,
    reference_longitude: float,
) -> tuple[float, float]:
    """Convert latitude/longitude to local east/north coordinates."""
    longitude_scale = (
        METERS_PER_DEGREE_LATITUDE
        * cos(radians(reference_latitude))
    )

    if isclose(longitude_scale, 0.0):
        raise ValueError(
            "Cannot create local coordinates near the geographic poles"
        )

    east_m = (
        longitude - reference_longitude
    ) * longitude_scale

    north_m = (
        latitude - reference_latitude
    ) * METERS_PER_DEGREE_LATITUDE

    return east_m, north_m


def _from_local_xy(
    east_m: float,
    north_m: float,
    reference_latitude: float,
    reference_longitude: float,
) -> tuple[float, float]:
    """Convert local east/north coordinates to latitude/longitude."""
    longitude_scale = (
        METERS_PER_DEGREE_LATITUDE
        * cos(radians(reference_latitude))
    )

    if isclose(longitude_scale, 0.0):
        raise ValueError(
            "Cannot create geographic coordinates near the poles"
        )

    latitude = (
        reference_latitude
        + north_m / METERS_PER_DEGREE_LATITUDE
    )

    longitude = (
        reference_longitude
        + east_m / longitude_scale
    )

    return latitude, longitude


def _xy_distance(
    point_1: tuple[float, float],
    point_2: tuple[float, float],
) -> float:
    return hypot(
        point_2[0] - point_1[0],
        point_2[1] - point_1[1],
    )


def _points_are_close(
    point_1: tuple[float, float],
    point_2: tuple[float, float],
    tolerance_m: float = 0.001,
) -> bool:
    return _xy_distance(point_1, point_2) <= tolerance_m


def _orientation(
    point_a: tuple[float, float],
    point_b: tuple[float, float],
    point_c: tuple[float, float],
) -> float:
    """Return the signed orientation of three local-coordinate points."""
    return (
        (point_b[0] - point_a[0])
        * (point_c[1] - point_a[1])
        - (point_b[1] - point_a[1])
        * (point_c[0] - point_a[0])
    )


def _point_is_on_segment(
    point: tuple[float, float],
    segment_start: tuple[float, float],
    segment_end: tuple[float, float],
) -> bool:
    if (
        abs(
            _orientation(
                segment_start,
                segment_end,
                point,
            )
        )
        > GEOMETRY_EPSILON
    ):
        return False

    return (
        min(segment_start[0], segment_end[0])
        - GEOMETRY_EPSILON
        <= point[0]
        <= max(segment_start[0], segment_end[0])
        + GEOMETRY_EPSILON
        and min(segment_start[1], segment_end[1])
        - GEOMETRY_EPSILON
        <= point[1]
        <= max(segment_start[1], segment_end[1])
        + GEOMETRY_EPSILON
    )


def _segments_intersect(
    first_start: tuple[float, float],
    first_end: tuple[float, float],
    second_start: tuple[float, float],
    second_end: tuple[float, float],
) -> bool:
    """Return True when two closed line segments intersect."""
    orientation_1 = _orientation(
        first_start,
        first_end,
        second_start,
    )
    orientation_2 = _orientation(
        first_start,
        first_end,
        second_end,
    )
    orientation_3 = _orientation(
        second_start,
        second_end,
        first_start,
    )
    orientation_4 = _orientation(
        second_start,
        second_end,
        first_end,
    )

    first_straddles = (
        orientation_1 > GEOMETRY_EPSILON
        and orientation_2 < -GEOMETRY_EPSILON
    ) or (
        orientation_1 < -GEOMETRY_EPSILON
        and orientation_2 > GEOMETRY_EPSILON
    )

    second_straddles = (
        orientation_3 > GEOMETRY_EPSILON
        and orientation_4 < -GEOMETRY_EPSILON
    ) or (
        orientation_3 < -GEOMETRY_EPSILON
        and orientation_4 > GEOMETRY_EPSILON
    )

    if first_straddles and second_straddles:
        return True

    if (
        abs(orientation_1) <= GEOMETRY_EPSILON
        and _point_is_on_segment(
            second_start,
            first_start,
            first_end,
        )
    ):
        return True

    if (
        abs(orientation_2) <= GEOMETRY_EPSILON
        and _point_is_on_segment(
            second_end,
            first_start,
            first_end,
        )
    ):
        return True

    if (
        abs(orientation_3) <= GEOMETRY_EPSILON
        and _point_is_on_segment(
            first_start,
            second_start,
            second_end,
        )
    ):
        return True

    return (
        abs(orientation_4) <= GEOMETRY_EPSILON
        and _point_is_on_segment(
            first_end,
            second_start,
            second_end,
        )
    )


def _point_is_inside_polygon(
    point: tuple[float, float],
    polygon: list[tuple[float, float]],
) -> bool:
    """Check polygon containment, treating the boundary as inside."""
    if len(polygon) < 3:
        return False

    for index in range(len(polygon)):
        edge_start = polygon[index]
        edge_end = polygon[(index + 1) % len(polygon)]

        if _point_is_on_segment(
            point,
            edge_start,
            edge_end,
        ):
            return True

    point_x, point_y = point
    inside = False
    previous_index = len(polygon) - 1

    for index in range(len(polygon)):
        current_x, current_y = polygon[index]
        previous_x, previous_y = polygon[previous_index]

        crosses_horizontal_ray = (
            current_y > point_y
        ) != (
            previous_y > point_y
        )

        if crosses_horizontal_ray:
            intersection_x = (
                (previous_x - current_x)
                * (point_y - current_y)
                / (previous_y - current_y)
                + current_x
            )

            if point_x < intersection_x:
                inside = not inside

        previous_index = index

    return inside


def _segment_intersects_polygon(
    segment_start: tuple[float, float],
    segment_end: tuple[float, float],
    polygon: list[tuple[float, float]],
) -> bool:
    """Check whether a segment enters or touches a polygon."""
    if _point_is_inside_polygon(segment_start, polygon):
        return True

    if _point_is_inside_polygon(segment_end, polygon):
        return True

    for index in range(len(polygon)):
        edge_start = polygon[index]
        edge_end = polygon[(index + 1) % len(polygon)]

        if _segments_intersect(
            segment_start,
            segment_end,
            edge_start,
            edge_end,
        ):
            return True

    midpoint = (
        (segment_start[0] + segment_end[0]) / 2.0,
        (segment_start[1] + segment_end[1]) / 2.0,
    )

    return _point_is_inside_polygon(midpoint, polygon)


def _deduplicate_points(
    points: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    if not points:
        return []

    result = [points[0]]

    for point in points[1:]:
        if not _points_are_close(point, result[-1]):
            result.append(point)

    return result


def _rectangle_anchors(
    point: tuple[float, float],
    minimum_x: float,
    maximum_x: float,
    minimum_y: float,
    maximum_y: float,
) -> list[tuple[float, float]]:
    """Project a point onto all four sides of a rectangle."""
    point_x, point_y = point

    clamped_x = min(max(point_x, minimum_x), maximum_x)
    clamped_y = min(max(point_y, minimum_y), maximum_y)

    candidates = [
        (minimum_x, clamped_y),
        (maximum_x, clamped_y),
        (clamped_x, minimum_y),
        (clamped_x, maximum_y),
    ]

    unique_candidates: list[tuple[float, float]] = []

    for candidate in candidates:
        if not any(
            _points_are_close(candidate, existing)
            for existing in unique_candidates
        ):
            unique_candidates.append(candidate)

    return unique_candidates


def _rectangle_perimeter_parameter(
    point: tuple[float, float],
    minimum_x: float,
    maximum_x: float,
    minimum_y: float,
    maximum_y: float,
) -> float:
    """Map a point on a rectangle boundary to perimeter distance."""
    point_x, point_y = point
    width = maximum_x - minimum_x
    height = maximum_y - minimum_y

    if isclose(point_y, minimum_y, abs_tol=GEOMETRY_EPSILON):
        return point_x - minimum_x

    if isclose(point_x, maximum_x, abs_tol=GEOMETRY_EPSILON):
        return width + point_y - minimum_y

    if isclose(point_y, maximum_y, abs_tol=GEOMETRY_EPSILON):
        return width + height + maximum_x - point_x

    if isclose(point_x, minimum_x, abs_tol=GEOMETRY_EPSILON):
        return 2.0 * width + height + maximum_y - point_y

    raise ValueError("Point is not on the detour rectangle boundary")


def _rectangle_perimeter_route(
    start: tuple[float, float],
    end: tuple[float, float],
    minimum_x: float,
    maximum_x: float,
    minimum_y: float,
    maximum_y: float,
    *,
    forward: bool,
) -> list[tuple[float, float]]:
    """Build one of the two perimeter routes between boundary points."""
    width = maximum_x - minimum_x
    height = maximum_y - minimum_y
    perimeter = 2.0 * (width + height)

    start_parameter = _rectangle_perimeter_parameter(
        start,
        minimum_x,
        maximum_x,
        minimum_y,
        maximum_y,
    )
    end_parameter = _rectangle_perimeter_parameter(
        end,
        minimum_x,
        maximum_x,
        minimum_y,
        maximum_y,
    )

    corners_with_parameters = [
        ((minimum_x, minimum_y), 0.0),
        ((maximum_x, minimum_y), width),
        ((maximum_x, maximum_y), width + height),
        (
            (minimum_x, maximum_y),
            2.0 * width + height,
        ),
    ]

    selected_corners: list[
        tuple[float, tuple[float, float]]
    ] = []

    if forward:
        route_distance = (
            end_parameter - start_parameter
        ) % perimeter

        for corner, corner_parameter in corners_with_parameters:
            offset = (
                corner_parameter - start_parameter
            ) % perimeter

            if (
                GEOMETRY_EPSILON
                < offset
                < route_distance - GEOMETRY_EPSILON
            ):
                selected_corners.append((offset, corner))
    else:
        route_distance = (
            start_parameter - end_parameter
        ) % perimeter

        for corner, corner_parameter in corners_with_parameters:
            offset = (
                start_parameter - corner_parameter
            ) % perimeter

            if (
                GEOMETRY_EPSILON
                < offset
                < route_distance - GEOMETRY_EPSILON
            ):
                selected_corners.append((offset, corner))

    selected_corners.sort(key=lambda item: item[0])

    route = [
        start,
        *[corner for _, corner in selected_corners],
        end,
    ]

    return _deduplicate_points(route)


def _plan_sade_zone_detour(
    current: tuple[float, float],
    target: tuple[float, float],
    vertices: list[tuple[float, float]],
    *,
    clearance_m: float,
) -> list[tuple[float, float]]:
    """Plan a shortest valid route around a polygonal SADE zone.

    Args:
        current: Current ``(latitude, longitude)``.
        target: Active mission item's ``(latitude, longitude)``.
        vertices: Zone vertices as ``(latitude, longitude)``.
        clearance_m: Distance between the zone bounding perimeter and the
            generated detour route.

    Returns:
        Detour waypoints as ``(latitude, longitude)``. The original mission
        target is intentionally excluded because MAVSDK resumes the original
        mission after reaching the final detour point.

    Raises:
        ValueError: If the input is invalid or no safe route can be found.
    """
    if len(vertices) < 3:
        raise ValueError(
            "At least three vertices are required for a SADE-zone detour"
        )

    if clearance_m <= 0:
        raise ValueError("clearance_m must be greater than zero")

    reference_latitude = sum(
        latitude for latitude, _ in vertices
    ) / len(vertices)

    reference_longitude = sum(
        longitude for _, longitude in vertices
    ) / len(vertices)

    polygon_xy = [
        _to_local_xy(
            latitude,
            longitude,
            reference_latitude,
            reference_longitude,
        )
        for latitude, longitude in vertices
    ]

    current_xy = _to_local_xy(
        current[0],
        current[1],
        reference_latitude,
        reference_longitude,
    )

    target_xy = _to_local_xy(
        target[0],
        target[1],
        reference_latitude,
        reference_longitude,
    )

    if _point_is_inside_polygon(current_xy, polygon_xy):
        raise ValueError(
            "Cannot begin lateral avoidance because the drone is "
            "horizontally inside the SADE zone"
        )

    if _point_is_inside_polygon(target_xy, polygon_xy):
        raise ValueError(
            "Cannot resume toward a mission waypoint inside the SADE zone"
        )

    # If the original mission segment does not intersect the polygon,
    # no lateral detour is necessary.
    if not _segment_intersects_polygon(
        current_xy,
        target_xy,
        polygon_xy,
    ):
        return []

    polygon_x_values = [
        point[0] for point in polygon_xy
    ]
    polygon_y_values = [
        point[1] for point in polygon_xy
    ]

    minimum_x = min(polygon_x_values) - clearance_m
    maximum_x = max(polygon_x_values) + clearance_m
    minimum_y = min(polygon_y_values) - clearance_m
    maximum_y = max(polygon_y_values) + clearance_m

    if (
        maximum_x - minimum_x <= GEOMETRY_EPSILON
        or maximum_y - minimum_y <= GEOMETRY_EPSILON
    ):
        raise ValueError("SADE zone has invalid polygon dimensions")

    current_anchors = _rectangle_anchors(
        current_xy,
        minimum_x,
        maximum_x,
        minimum_y,
        maximum_y,
    )

    target_anchors = _rectangle_anchors(
        target_xy,
        minimum_x,
        maximum_x,
        minimum_y,
        maximum_y,
    )

    best_route: list[tuple[float, float]] | None = None
    best_distance = float("inf")

    for current_anchor in current_anchors:
        if _segment_intersects_polygon(
            current_xy,
            current_anchor,
            polygon_xy,
        ):
            continue

        for target_anchor in target_anchors:
            if _segment_intersects_polygon(
                target_anchor,
                target_xy,
                polygon_xy,
            ):
                continue

            for forward in (True, False):
                perimeter_route = _rectangle_perimeter_route(
                    current_anchor,
                    target_anchor,
                    minimum_x,
                    maximum_x,
                    minimum_y,
                    maximum_y,
                    forward=forward,
                )

                complete_route = _deduplicate_points(
                    [
                        current_xy,
                        *perimeter_route,
                        target_xy,
                    ]
                )

                route_is_valid = True

                for index in range(len(complete_route) - 1):
                    if _segment_intersects_polygon(
                        complete_route[index],
                        complete_route[index + 1],
                        polygon_xy,
                    ):
                        route_is_valid = False
                        break

                if not route_is_valid:
                    continue

                route_distance = sum(
                    _xy_distance(
                        complete_route[index],
                        complete_route[index + 1],
                    )
                    for index in range(len(complete_route) - 1)
                )

                if route_distance < best_distance:
                    best_distance = route_distance
                    best_route = perimeter_route

    if best_route is None:
        raise ValueError(
            "No non-intersecting route around the SADE zone was found"
        )

    # Exclude the current position and original target. Only temporary
    # perimeter points should be passed to goto_location().
    detour_xy = [
        point
        for point in _deduplicate_points(best_route)
        if not _points_are_close(point, current_xy)
        and not _points_are_close(point, target_xy)
    ]

    return [
        _from_local_xy(
            east_m=point[0],
            north_m=point[1],
            reference_latitude=reference_latitude,
            reference_longitude=reference_longitude,
        )
        for point in detour_xy
    ]



class ResilientDrone:
    """Wraps mavsdk.System to automatically handle drone reconnection.

    All critical operations are retried transparently.
    """

    def __init__(
        self,
        listen_port: str,
        drone_id: int,
        mavsdk_port: int,
        max_retries: int = 10,
        retry_delay: int = 5,
        schema: str = "udpin://",
        host: str = "0.0.0.0",  # nosec B104 - deliberately binds to all interfaces for MAVLink UDP
    ) -> None:
        self.drone_id = drone_id
        self._listen_port = listen_port
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._system = System(port=mavsdk_port)
        self._connected = False
        self._schema = schema
        self._host = host
        self._system_address = f"{self._schema}{self._host}:{self._listen_port}"
        self._zones = SadeZones()
        self._nearby_check = None
        self._nearby_zones = {}
        self._mission_speed = float("inf")
        self._approaching_sade_zone = None
        self.home_mission = []
        self.mission_plan = []
        self.current_progress_mission = 0
        self.coordinate_based_missions = True
        self.executed_go_home = False
        self._avoiding_sade_zone = False
        self._detoured_sade_zones: set[str] = set()

    def set_home_mission(self, home_mission: list[MissionItem]):
        self.home_mission = home_mission

    def get_home_mission(self) -> list[MissionItem]:
        return self.home_mission

    async def capture_drone_maximum_speed(self):
        return await self._system.param.get_param_float("MPC_XY_CRUISE")

    @property
    def _log_prefix(self) -> str:
        return f"D{self.drone_id:02d} | "

    def log(self, message: str) -> None:
        log.info(f"{self._log_prefix} {message}")

    def log_warning(self, message: str) -> None:
        log.warning(f"{self._log_prefix} {message}")

    def log_error(self, message: str) -> None:
        log.error(f"{self._log_prefix} {message}")


    async def _wait_until_location_reached(
        self,
        latitude: float,
        longitude: float,
        *,
        acceptance_radius_m: float,
        timeout_s: float,
    ) -> None:
        """Wait until telemetry reports that a location has been reached."""
        if acceptance_radius_m <= 0:
            raise ValueError("acceptance_radius_m must be greater than zero")

        if timeout_s <= 0:
            raise ValueError("timeout_s must be greater than zero")

        try:
            async with asyncio.timeout(timeout_s):
                async for position in self.telemetry_position():
                    distance_m = _horizontal_distance_m(
                        position.latitude_deg,
                        position.longitude_deg,
                        latitude,
                        longitude,
                    )

                    if distance_m <= acceptance_radius_m:
                        self.log(
                            "Reached detour waypoint "
                            f"{latitude:.7f}, {longitude:.7f} "
                            f"within {distance_m:.1f} meters"
                        )
                        return
        except TimeoutError as error:
            msg = (
                "Timed out navigating to detour waypoint "
                f"{latitude:.7f}, {longitude:.7f}"
            )
            raise TimeoutError(msg) from error

        raise RuntimeError("Position telemetry stream ended unexpectedly")


    async def navigate_around_sade_zone(
        self,
        zone_id: str,
        *,
        clearance_m: float = 20.0,
        acceptance_radius_m: float = 5.0,
        waypoint_timeout_s: float = 120.0,
    ) -> bool:
        """Navigate around a SADE zone, then resume the original mission.

        The mission stored on the vehicle is not cleared, modified, or
        re-uploaded. Temporary movement around the zone uses goto_location().
        """
        if self._avoiding_sade_zone:
            self.log_warning(
                "A SADE-zone avoidance maneuver is already active"
            )
            return False

        zone = self._zones.get_sade_zone(zone_id)

        if zone is None:
            self.log_error(f"Cannot find SADE zone: {zone_id}")
            await self.hold()
            return False

        self._avoiding_sade_zone = True

        try:
            # Keep the existing mission uploaded but stop it from advancing.
            await self.mission_pause()
            await self.hold()

            mission_items, current_index = (
                await self.download_current_mission_state()
            )

            if not mission_items:
                raise ValueError(
                    "The currently uploaded mission is empty"
                )

            if current_index is None:
                # The mission has not started. Its first item is the target.
                target_index = 0
            elif current_index >= len(mission_items):
                raise ValueError(
                    "The original mission has already completed"
                )
            else:
                target_index = current_index

            target_item = mission_items[target_index]

            # Ignore altitude here because this is specifically a lateral
            # avoidance maneuver.
            if zone.is_inside(
                target_item.latitude_deg,
                target_item.longitude_deg,
            ):
                raise ValueError(
                    f"Mission waypoint {target_index} is inside "
                    f"SADE zone {zone_id}; remaining in hold mode"
                )

            (
                current_latitude,
                current_longitude,
                absolute_altitude,
            ) = await self.fetch_drone_position()

            detour_waypoints = _plan_sade_zone_detour(
                current=(
                    current_latitude,
                    current_longitude,
                ),
                target=(
                    target_item.latitude_deg,
                    target_item.longitude_deg,
                ),
                vertices=[
                    (vertex.latitude, vertex.longitude)
                    for vertex in zone.vertices
                ],
                clearance_m=clearance_m,
            )

            if isfinite(self._mission_speed):
                await self._system.action.set_current_speed(
                    self._mission_speed
                )

            if not detour_waypoints:
                self.log(
                    f"The path to mission waypoint {target_index} "
                    f"does not cross {zone_id}; resuming mission"
                )

                await self.mission_resume()
                return True

            self.log(
                f"Navigating around {zone_id} using "
                f"{len(detour_waypoints)} temporary waypoints"
            )

            for waypoint_number, (
                latitude,
                longitude,
            ) in enumerate(detour_waypoints, start=1):
                self.log(
                    f"Flying to detour waypoint "
                    f"{waypoint_number}/{len(detour_waypoints)}: "
                    f"{latitude:.7f}, {longitude:.7f}"
                )

                # goto_location() requires absolute altitude. MissionItem stores
                # relative altitude, so retain the current absolute altitude.
                await self.go_to_location(
                    latitude,
                    longitude,
                    absolute_altitude,
                    0.0,
                )

                await self._wait_until_location_reached(
                    latitude,
                    longitude,
                    acceptance_radius_m=acceptance_radius_m,
                    timeout_s=waypoint_timeout_s,
                )

            self.log(
                f"Finished navigating around {zone_id}; "
                f"resuming mission at waypoint {target_index}"
            )

            # The original mission was never cleared or re-uploaded, so this
            # continues from the flight controller's stored mission index.
            await self.mission_resume()

            self._detoured_sade_zones.add(zone_id)
            return True

        except Exception as error:  # noqa: BLE001
            self.log_error(
                f"Failed to navigate around SADE zone {zone_id}: {error}"
            )

            try:
                await self.hold()
            except Exception as hold_error:  # noqa: BLE001
                self.log_error(
                    "Failed to enter hold mode after detour failure: "
                    f"{hold_error}"
                )

            return False

        finally:
            self._nearby_zones = {}
            self._approaching_sade_zone = None
            self._avoiding_sade_zone = False


    async def connect(self) -> None:
        attempt = 0
        while attempt < self._max_retries:
            try:
                self.log(
                    f"Connecting as {self._system_address} "
                    f"(attempt {attempt + 1}/{self._max_retries})…"
                )
                await self._system.connect(system_address=self._system_address)
                async for state in self._system.core.connection_state():
                    if state.is_connected:
                        self.log("connected!")
                        self._connected = True
                        self._mission_speed = await self.capture_drone_maximum_speed()
                        return
                log.warning(
                    f"Connection state lost before establishing. "
                    f"Retrying in {self._retry_delay}s…"
                )
            except grpc.aio.AioRpcError as e:
                msg = (
                    f"gRPC error during connection: {e}. "
                    f"Retrying in {self._retry_delay}s…"
                )
                log.error(msg)
            attempt += 1
            await asyncio.sleep(self._retry_delay)
        log.error(
            f"Failed to connect to Drone '{self.drone_id}' "
            f"after {self._max_retries} attempts."
        )
        msg = f"Could not connect to drone after {self._max_retries} attempts."
        raise ConnectionError(msg)

    async def ensure_connected(self) -> None:
        if not self._connected:
            await self.connect()

    async def wait_for_global_position_estimate(self) -> None:
        async for health in self.telemetry_health():
            self.log(f"Global position ok: {health.is_global_position_ok}")
            if health.is_global_position_ok:
                self.log("Global position estimate ok")
                break

    async def fetch_drone_position(self):
        current_latitude: float | None = None
        current_longitude: float | None = None
        current_altitude: float | None = None

        async for position in self.telemetry_position():
            current_latitude = position.latitude_deg
            current_longitude = position.longitude_deg
            current_altitude = position.absolute_altitude_m
            break

        if not isinstance(current_altitude, float):
            msg = f"Failed to get current drone altitude: {current_altitude}"
            log.error(msg)
            raise TypeError(msg)

        if current_latitude is None or current_longitude is None:
            msg = "Failed to get current drone position."
            self.log(msg)
            raise ValueError(msg)
        return current_latitude, current_longitude, current_altitude

    async def close_monitoring(
        self,
        nearby_zones: dict[str, float] | float,
    ):
        if self._avoiding_sade_zone:
            return

        if not isinstance(nearby_zones, dict) or not nearby_zones:
            return

        if not self._nearby_zones:
            self._nearby_zones = nearby_zones.copy()

            self._mission_speed = (
                await self.capture_drone_maximum_speed()
            )

            await self._system.action.set_current_speed(
                self._mission_speed * 0.2
            )
            return

        approaching_zones = [
            (zone_id, current_distance)
            for zone_id, current_distance in nearby_zones.items()
            if (
                zone_id in self._nearby_zones
                and current_distance
                < self._nearby_zones[zone_id]
            )
        ]

        self._nearby_zones = nearby_zones.copy()

        if not approaching_zones:
            return

        zone_id, min_distance = min(
            approaching_zones,
            key=lambda zone_and_distance: zone_and_distance[1],
        )

        self._approaching_sade_zone = zone_id

        if min_distance >= ZONE_REQUEST_THRESHOLD_METERS:
            return

        await self.mission_pause()

        try:
            sade_zone_lease = (
                await self._zones.request_sade_zone_entry(
                    drone=self,
                    zone_sade_id=zone_id,
                    emulate_wait=True,
                )
            )

            if isfinite(self._mission_speed):
                await self._system.action.set_current_speed(
                    self._mission_speed
                )

            if sade_zone_lease:
                self.log(
                    "SADEZone access granted until "
                    f"{sade_zone_lease.expiration_time}"
                )

                # The mission remains uploaded. No reset, download/upload, or
                # altitude-adjusted replacement mission is necessary.
                self.log(
                    f"Access to {zone_id} was granted; "
                    "resuming original mission"
                )
                await self.mission_resume()

            else:
                self.log_warning(
                    f"Access to SADE zone {zone_id} was not granted; "
                    "checking whether a detour is required"
                )

                detour_completed = (
                    await self.navigate_around_sade_zone(
                        zone_id,
                        clearance_m=20.0,
                        acceptance_radius_m=5.0,
                        waypoint_timeout_s=120.0,
                    )
                )

                if not detour_completed:
                    self.log_error(
                        f"Could not safely navigate around {zone_id}; "
                        "remaining in hold mode"
                    )

        finally:
            self._nearby_zones = {}


    async def check_inside_sade_zones(self):
        if self._avoiding_sade_zone:
            return

        (
            current_latitude,
            current_longitude,
            current_altitude,
        ) = await self.fetch_drone_position()

        inside, nearby_result = self._zones.classify_point_inside_zone(
            current_latitude,
            current_longitude,
            current_altitude,
            self.drone_id,
        )

        if isinstance(nearby_result, dict):
            raw_nearby_zones = nearby_result
        else:
            raw_nearby_zones = {}

        # Once the drone has completely left every zone's nearby threshold,
        # allow those zones to be detected again in a future mission segment.
        if not raw_nearby_zones:
            self._detoured_sade_zones.clear()

        nearby_zones = {
            zone_id: distance
            for zone_id, distance in raw_nearby_zones.items()
            if zone_id not in self._detoured_sade_zones
        }

        if inside is not None:
            self.log_error(
                f"Drone is inside SADE zone {inside}"
            )
            self._nearby_zones = {}

        elif nearby_zones:
            self.log("Drone is nearby one or more SADE zones")
            await self.close_monitoring(nearby_zones)

        else:
            self.log("Drone is outside the monitored SADE zones")
            self._nearby_zones = {}


    async def hold(self):
        await self._system.action.hold()

    async def mission_resume(self):
        await self._system.mission.start_mission()

    async def mission_pause(self):
        await self._system.mission.pause_mission()

    async def _retry(
        self,
        coro_func: Callable,  # pyright: ignore[reportMissingTypeArgument]
        *args: object,
        **kwargs: object,
    ) -> object:
        attempt = 0
        while attempt < self._max_retries:
            try:
                await self.ensure_connected()
                return await coro_func(*args, **kwargs)
            except grpc.aio.AioRpcError as e:
                log.error(
                    f"gRPC error during operation: {e}. Reconnecting and retrying…"
                )
                self._connected = False
                await asyncio.sleep(self._retry_delay)
            attempt += 1
        msg = f"Operation failed after {self._max_retries} retries."
        log.error(msg)
        raise ConnectionError(msg)

    # Proxy methods for drone operations
    async def telemetry_position(self):
        async for position in self._system.telemetry.position():
            yield position

    async def telemetry_health(self):
        self.log("Monitoring telemetry health")
        async for health in self._system.telemetry.health():
            yield health

    async def action_arm(self):
        self.log("Arming")
        await self._retry(self._system.action.arm)

    async def action_takeoff(self):
        self.log("Taking off")
        await self._retry(self._system.action.takeoff)

    async def action_land(self):
        self.log("Landing")
        await self._retry(self._system.action.land)

    async def mission_upload_mission(self, mission_plan):
        self.log("Uploading mission")
        await self._retry(self._system.mission.upload_mission, mission_plan)

    async def mission_start_mission(self):
        self.log("Starting mission")
        await self._retry(self._system.mission.start_mission)

    async def mission_mission_progress(self):
        self.log("Monitoring mission progress")
        async for progress in self._system.mission.mission_progress():
            yield progress

    async def mission_clear(self):
        """Clear the current mission."""
        self.log("Clearing mission")
        await self._retry(self._system.mission.clear_mission)

    async def return_to_launch(self):
        """Return to launch position (home)."""
        self.log("Returning to launch")
        await self._retry(self._system.action.return_to_launch)

    async def go_to_location(
        self, latitude: float, longitude: float, altitude: float, yaw: float
    ):
        self.log("Going to location")
        await self._retry(
            self._system.action.goto_location, latitude, longitude, altitude, yaw
        )

    async def download_current_mission_state(
        self,
        *,
        progress_timeout_s: float = 5.0,
    ) -> tuple[list[MissionItem], int | None]:
        """Download the active mission and determine its current item.

        Returns:
            A tuple containing:

            - The mission items currently stored on the vehicle.
            - The current item index, or None if the mission has not started.
        """
        self.log("Downloading current mission state")

        mission_plan = await self._system.mission.download_mission()
        mission_items = mission_plan.mission_items

        self.log(
            f"Downloaded {len(mission_items)} mission items"
        )

        current_index: int | None = None
        reported_total: int | None = None

        try:
            async with asyncio.timeout(progress_timeout_s):
                async for progress in self.mission_mission_progress():
                    reported_total = progress.total

                    if progress.current < 0:
                        current_index = None
                    else:
                        current_index = progress.current
                        self.current_progress_mission = progress.current

                    self.log(
                        "Mission progress sample: "
                        f"current={progress.current}, "
                        f"total={progress.total}"
                    )
                    break

        except TimeoutError:
            # The main mission-progress monitor normally keeps this property
            # current. Use it as a fallback if a second stream sample times out.
            fallback_index = self.current_progress_mission

            if fallback_index >= 0:
                current_index = fallback_index

            self.log_warning(
                "Timed out waiting for a mission-progress sample; "
                f"using stored index {current_index}"
            )

        if (
            reported_total is not None
            and reported_total != len(mission_items)
        ):
            self.log_warning(
                "Downloaded mission count differs from mission progress: "
                f"downloaded={len(mission_items)}, "
                f"reported={reported_total}"
            )

        for index, item in enumerate(mission_items):
            if current_index is None:
                status = "pending"
            elif index < current_index:
                status = "finished"
            elif index == current_index:
                status = "current"
            else:
                status = "pending"

            self.log(
                f"Mission waypoint {index}: {status} "
                f"(lat={item.latitude_deg:.7f}, "
                f"lon={item.longitude_deg:.7f}, "
                f"rel_alt={item.relative_altitude_m:.1f})"
            )

        return mission_items, current_index

    async def core_connection_state(self):
        self.log("Monitoring core connection state")
        async for state in self._system.core.connection_state():
            yield state

    async def return_to_home(self):
        """Execute return to home mission."""
        if not self.home_mission:
            self.log_error("Cannot return home: home_mission is empty!")
            return

        self.log(f"Executing return to home with {len(self.home_mission)} waypoints")

        # Stop current mission first
        try:
            await self._system.mission.pause_mission()
            await asyncio.sleep(0.5)
        # ruff: noqa: BLE001
        except Exception as e:
            self.log(f"Could not pause mission: {e}")

        # Clear the current mission
        try:
            await self.mission_clear()
            await asyncio.sleep(0.5)
        # ruff: noqa: BLE001
        except Exception as e:
            self.log(f"Could not clear mission: {e}")

        # Upload and start home mission
        home_plan = MissionPlan(self.home_mission)
        self.log("Uploading return home mission...")
        await self.mission_upload_mission(home_plan)

        self.log("Starting return home mission...")
        await self.mission_start_mission()
        await asyncio.sleep(2)

        # Monitor until complete (without checking get_set_home to avoid early exit)
        self.log("Monitoring return home progress...")
        async for progress in self.mission.mission_progress():
            self._report_mission_progress(progress)
            if progress.current == progress.total:
                self.log("Return home mission completed!")
                break

    @property
    def mission(self) -> Mission:
        return self._system.mission

    async def execute_mission(
        self, mission_steps: list[MissionStep] | list[MissionItem]
    ) -> None:
        self._current_mission = mission_steps
        _current_mission_items = [step.create_mission_item() for step in mission_steps]
        mission_plan = MissionPlan(_current_mission_items)
        self.log("Uploading mission")
        while True:
            try:
                await self.mission.upload_mission(mission_plan)
                break
            except MissionError:
                log.warning("Mission upload failed, retrying in 5 seconds")
                sleep_time: int = 5
                await asyncio.sleep(sleep_time)

        self.log("Starting mission")
        await self.mission.start_mission()
        await asyncio.sleep(2)

        # Monitor mission progress
        await self._monitor_mission_progress()

    async def _monitor_mission_progress(self) -> None:
        retries_left = 5
        spaced_sleep_sec = 2

        # log first mission item description separately
        self._log_mission_item_description_progress(item_idx=0)

        while retries_left > 0:
            try:
                async for progress in self.mission.mission_progress():
                    self.current_progress_mission = progress.current
                    self._report_mission_progress(progress)
                    if progress.current == progress.total:
                        self.log("Mission completed")
                        break
            except grpc.aio.AioRpcError as e:
                if getattr(e, "code", lambda: None)() == grpc.StatusCode.UNAVAILABLE:
                    self.log_error(
                        f"Mission progress stream unavailable: {e.details()}. "
                        "Socket may be closed. "
                        "Skipping mission progress monitoring."
                    )
                else:
                    self.log_error(
                        f"Unexpected gRPC error during mission progress: {e}"
                    )
                if retries_left > 1:
                    await asyncio.sleep(spaced_sleep_sec)
                    spaced_sleep_sec *= 2
                    retries_left -= 1
                    await self.connect()
                    continue
                raise
            break

    def _report_mission_progress(self, progress: MissionProgress) -> None:
        self._log_mission_item_description_progress(
            item_idx=progress.current, total_count=progress.total
        )

    def _log_mission_item_description_progress(
        self,
        item_idx: int,
        total_count: int | None = None,
    ):
        # simple validation
        if total_count is None:
            total_count = len(self._current_mission)
        elif total_count != len(self._current_mission):
            log.warning(
                "Total mission count mismatch: "
                f"{total_count} != {len(self._current_mission)}"
            )

        # log progress with item's description if possible
        if item_idx >= total_count or item_idx > len(self._current_mission):
            msg = f"Mission progress: {item_idx}/{total_count}"
        else:
            try:
                item = self._current_mission[item_idx]
                msg = f"\t{item_idx + 1}/{total_count}: {item.description}"
            except IndexError:
                log.warning(f"Mission item not found: {item_idx}")
                msg = f"Mission progress: {item_idx}/{total_count}"
        self.log(msg)


def _create_mission_item(
    lat: float, lon: float, alt: float, speed: float, is_fly_through=True
) -> MissionItem:
    """A mission item may contain position and/or actions that describe a mission step.

    https://mavsdk.mavlink.io/main/en/cpp/api_reference/structmavsdk_1_1_mission_1_1_mission_item.html#data-fields
    """
    if not (
        MIN_LAT <= lat <= MAX_LAT or isclose(lat, MIN_LAT) or isclose(lat, MAX_LAT)
    ):
        msg = f"Latitude out of range: {lat}"
        raise ValueError(msg)
    if not (
        MIN_LON <= lon <= MAX_LON or isclose(lon, MIN_LON) or isclose(lon, MAX_LON)
    ):
        msg = f"Longitude out of range: {lon}"
        raise ValueError(msg)
    if not (speed >= MIN_SPEED or isclose(speed, MIN_SPEED)):
        msg = f"Speed must be non-negative: {speed}"
        raise ValueError(msg)
    return MissionItem(
        latitude_deg=lat,
        longitude_deg=lon,
        relative_altitude_m=alt,
        speed_m_s=speed,
        is_fly_through=is_fly_through,  # The drone will fly through the waypoint without stopping
        gimbal_pitch_deg=float("nan"),
        gimbal_yaw_deg=float("nan"),
        camera_action=MissionItem.CameraAction.NONE,
        loiter_time_s=float("nan"),
        camera_photo_interval_s=float("nan"),
        camera_photo_distance_m=float("nan"),
        acceptance_radius_m=float("nan"),
        yaw_deg=float("nan"),
        vehicle_action=MissionItem.VehicleAction.NONE,  # No specific vehicle action
    )


def compare_mission_items(item1: MissionItem, item2: MissionItem):
    return (
        item1.latitude_deg == item2.latitude_deg
        and item1.longitude_deg == item2.longitude_deg
    )
