"""Wrapper class for UAV."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from math import isclose

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
from .config import SURVELLIANCE_DRONE_IDS_MAX
from .config import ZONE_REQUEST_THRESHOLD_METERS
from .config import get_origin
from .zones import SadeZoneLease
from .zones import SadeZones

NEARBY_RECHECK_INTERVAL = 1


@dataclass
class NED:
    """North-East-Down coordinates."""

    north: float
    east: float
    down: float


@dataclass
class MissionStep:
    """Represents a single step in a waypoint-based mission."""

    short_name: str
    description: str
    ned: NED
    home_alt: float
    speed: float
    home: Lla

    def create_mission_item(self) -> MissionItem:
        """Creates a MissionItem based on the NED coordinates relative to home."""
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
        result = self.home.move_ned(
            north=self.ned.north, east=self.ned.east, down=self.ned.down
        )
        if not isinstance(result, Lla):
            msg = "move_ned did not return Lla type"
            raise TypeError(msg)
        return result


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
        self._set_home_set = False
        self._nearby_zones = {}
        self._mission_speed = float("inf")
        self._approaching_sade_zone = None
        self.home_mission = []
        self.mission_plan = []
        self.current_progress_mission = 0
        self.coordinate_based_missions = True
        self.executed_go_home = False

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

    def get_set_home(self):
        return self._set_home_set

    def set_set_home(self, value):
        self._set_home_set = value

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

    async def close_monitoring(self, nearby_zones: dict[str, float] | float):
        if self._nearby_zones and isinstance(nearby_zones, dict):
            # now calculate the which zone is decreasing that means
            # the drone is approaching it
            # we already slowed down the drone speed now watch in which
            # zone it is approaching
            min_zone = None
            min_distance = float("inf")
            for zone_id in self._nearby_zones:
                if min_zone and self._nearby_zones[zone_id] > nearby_zones.get(
                    zone_id, float("inf")
                ):
                    min_zone = zone_id
                    min_distance = nearby_zones.get(zone_id, float("inf"))
                else:
                    min_zone = zone_id
                    min_distance = nearby_zones.get(zone_id, float("inf"))
            # now we know what zone it is approaching
            self._approaching_sade_zone = min_zone
            # check if the drone is less than threshold limit to
            # request the sade zone permission
            if min_distance < ZONE_REQUEST_THRESHOLD_METERS:
                await self.mission_pause()
                sade_zone_lease: (
                    SadeZoneLease | None
                ) = await self._zones.request_sade_zone_entry(
                    drone=self,
                    zone_sade_id=self._approaching_sade_zone,
                    emulate_wait=True,
                )
                # fetching the current position for increasing the altitude
                (
                    current_lat,
                    current_lon,
                    current_alt,
                ) = await self.fetch_drone_position()
                await self._system.action.set_current_speed(self._mission_speed)
                if sade_zone_lease:
                    self.log(
                        f"SADEZone access grant until {sade_zone_lease.expiration_time}"
                    )
                    await self.go_to_location(
                        current_lat,
                        current_lon,
                        current_alt * 2,
                        0.0,  # yaw (0.0 = unchanged, for many firmwares)
                    )
                    await asyncio.sleep(20)
                    if self.coordinate_based_missions:
                        await self.reset_and_execute_mission_case_study()
                    await self.reset_and_execute_mission()
                # reset the class things
                self._nearby_zones = {}
        else:
            self._nearby_zones = nearby_zones
            # slow down the drone speed
            # before slowing down capture the mission speed
            self._mission_speed = await self.capture_drone_maximum_speed()
            # now we can slow down the drone speed to 20 percent
            await self._system.action.set_current_speed(self._mission_speed * 0.2)

    async def check_inside_sade_zones(self):
        (
            current_latitude,
            current_longitude,
            current_altitude,
        ) = await self.fetch_drone_position()
        inside, nearby = self._zones.classify_point_inside_zone(
            current_latitude, current_longitude, current_altitude, self.drone_id
        )
        if self.get_set_home():
            if not self.executed_go_home:
                await self.mission_clear()
                await self.execute_mission(mission_steps=self.get_home_mission())
                self.executed_go_home = True
            self.log("Return home flag set, skipping zone checks")
            return
        if inside is not None:
            msg = "Drone is inside the defined zones!!!"
            self.log(msg)
            # every time reset the nearby zones as
            # we might be inside a zone that is not nearby
            self._nearby_zones = {}
        elif nearby:
            msg = "Drone is nearby one of the sade zones."
            self.log(msg)
            await self.close_monitoring(nearby)
        else:
            self.log("Drone is outside one of the defined zones")

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
        if isinstance(mission_steps[0], MissionStep):
            self._current_mission = mission_steps
            execute_coordinates = True
            allowed_short_desc = ["takeoff", "return_to_base"]
            for i in self._current_mission:
                if i.short_name in allowed_short_desc:
                    execute_coordinates = False
            if (
                self.coordinate_based_missions
                and execute_coordinates
                and self.drone_id <= SURVELLIANCE_DRONE_IDS_MAX
            ):
                # we will only creat the cooridnate accurate mission
                lat, lon, alt = get_origin()
                self.mission_plan = [_create_mission_item(lat, lon, alt, speed=20.0)]
            else:
                self.mission_plan = [
                    step.create_mission_item() for step in mission_steps
                ]
        else:
            self.mission_plan = mission_steps
        mission_plan_mission_plan = MissionPlan(self.mission_plan)
        self.log("Uploading mission")
        while True:
            try:
                await self.mission.upload_mission(mission_plan_mission_plan)
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

    async def reset_and_execute_mission(self):
        self.log("Downloading current mission...")
        mission_plan = await self._system.mission.download_mission()
        mission_items = mission_plan.mission_items

        self.log(f"Original mission has {len(mission_items)} items")

        # Create new mission items with adjusted altitude
        new_items = []
        for i, item in enumerate(mission_items):
            new_rel_alt = item.relative_altitude_m * 2

            new_item = MissionItem(
                latitude_deg=item.latitude_deg,
                longitude_deg=item.longitude_deg,
                relative_altitude_m=new_rel_alt,
                speed_m_s=item.speed_m_s,
                is_fly_through=item.is_fly_through,
                gimbal_pitch_deg=float("nan"),
                gimbal_yaw_deg=float("nan"),
                camera_action=MissionItem.CameraAction.NONE,
                loiter_time_s=float("nan"),
                camera_photo_interval_s=float("nan"),
                camera_photo_distance_m=float("nan"),
                acceptance_radius_m=float("nan"),
                yaw_deg=float("nan"),
                vehicle_action=MissionItem.VehicleAction.NONE,
            )

            # Check if this item should be included in the new mission
            for j in self.mission_plan[self.current_progress_mission :]:
                if compare_mission_items(j, new_item):
                    new_items.append(new_item)
                    self.log(
                        f"""Item {i}:
                            {item.relative_altitude_m:.1f}
                            -> {new_rel_alt:.1f} m"""
                    )
                    break  # Only add once, then move to next item

        # Validate mission before upload
        if not new_items:
            self.log("WARNING: No mission items to upload, keeping original mission")
            return

        new_plan = MissionPlan(new_items)
        self.log(f"New mission has {len(new_items)} items")

        # Stop current mission before uploading new one
        self.log("Pausing current mission before upload...")
        try:
            await self._system.mission.pause_mission()
            await asyncio.sleep(1)  # Give time for pause to take effect
        # ruff: noqa: BLE001
        except Exception as e:
            self.log(f"Could not pause mission: {e}, continuing anyway...")

        # Use the robust upload method with retry mechanism
        self.log("Uploading new mission...")
        await self.mission_upload_mission(new_plan)

        self.log("Starting new mission after sade zone approval")
        await self.mission_start_mission()
        await asyncio.sleep(2)

        # Monitor mission progress
        await self._monitor_mission_progress()

    async def reset_and_execute_mission_case_study(self):
        self.log("Original mission is what executing")

        lat, lon, alt = get_origin()
        new_items = [
            _create_mission_item(lat, lon, alt * 2, speed=20.0, is_fly_through=False)
        ]
        # Validate mission before upload
        if not new_items:
            self.log("WARNING: No mission items to upload, keeping original mission")
            return

        new_plan = MissionPlan(new_items)
        self.log(f"New mission has {len(new_items)} items")

        # Stop current mission before uploading new one
        self.log("Pausing current mission before upload...")
        try:
            await self._system.mission.pause_mission()
            await asyncio.sleep(1)  # Give time for pause to take effect
        # ruff: noqa: BLE001
        except Exception as e:
            self.log(f"Could not pause mission: {e}, continuing anyway...")

        # Use the robust upload method with retry mechanism
        self.log("Uploading new mission...")
        await self.mission_upload_mission(new_plan)

        self.log("Starting new mission after sade zone approval")
        await self.mission_start_mission()
        await asyncio.sleep(2)

        # Monitor mission progress
        await self._monitor_mission_progress()

    async def _monitor_mission_progress(self) -> None:
        retries_left = 5
        spaced_sleep_sec = 2

        # log first mission item description separately
        self._log_mission_item_description_progress(item_idx=0)

        while retries_left > 0 and not self.get_set_home():
            try:
                async for progress in self.mission.mission_progress():
                    self.current_progress_mission = progress.current
                    if self.get_set_home():
                        self.log("return home command issued so going home")
                        self.log(f"progress is {progress.current}")
                        return
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
