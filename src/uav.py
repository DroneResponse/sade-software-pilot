"""Wrapper class for UAV."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from math import isclose
from turtle import pos

import grpc
from droneresponse_mathtools import Lla
from loguru import logger as log
from mavsdk import System
from mavsdk.mission import (
    Mission,
    MissionError,
    MissionItem,
    MissionPlan,
    MissionProgress,
)

MAX_LAT = 90
MIN_LAT = -MAX_LAT
MAX_LON = 180
MIN_LON = -MAX_LON
MIN_SPEED = 0


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
    move_lla: LatLongAlt | None

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


class ResilientDrone:
    """Wraps mavsdk.System to automatically handle drone reconnection.

    All critical operations are retried transparently.
    """

    def __init__(
        self,
        listen_port: int,
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

    @property
    def _log_prefix(self) -> str:
        return f"D{self.drone_id:02d} | "

    def log(self, message: str) -> None:
        log.info(f"{self._log_prefix} {message}")

    def log_warning(self, message: str) -> None:
        log.warning(f"{self._log_prefix} {message}")

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

    async def core_connection_state(self):
        self.log("Monitoring core connection state")
        async for state in self._system.core.connection_state():
            yield state

    @property
    def mission(self) -> Mission:
        return self._system.mission

    async def execute_mission(self, mission_steps: list[MissionStep]) -> None:
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
                    self._report_mission_progress(progress)
                    if progress.current == progress.total:
                        self.log("Mission completed")
                        break
            except grpc.aio.AioRpcError as e:
                if getattr(e, "code", lambda: None)() == grpc.StatusCode.UNAVAILABLE:
                    log.error(
                        f"Mission progress stream unavailable: {e.details()}. "
                        "Socket may be closed. "
                        "Skipping mission progress monitoring."
                    )
                else:
                    log.error(f"Unexpected gRPC error during mission progress: {e}")
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
    lat: float, lon: float, alt: float, speed: float
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
        is_fly_through=True,  # The drone will fly through the waypoint without stopping
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
