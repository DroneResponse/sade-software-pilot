# Software Pilot API Reference

Complete API documentation for the SADE Software Pilot package.

## Table of Contents

1. [Configuration](#configuration)
2. [ResilientDrone](#resilientdrone)
3. [Mission Planning](#mission-planning)
4. [SADE Zone Access](#sade-zone-access)
5. [Telemetry](#telemetry)
6. [Exceptions](#exceptions)

---

## Configuration

### `PilotConfig`

Configuration object passed to pilots at startup.

```python
from software_pilot.config import PilotConfig

config = PilotConfig(
    drone_id=0,
    mavsdk_port=14550,
    mavlink_port=14540,
    mqtt_broker_address="localhost:1883",
    sade_zone_config_path=Path("/etc/pilot/zones.json"),
    custom_settings={"param1": "value1"}
)
```

#### Attributes

| Attribute               | Type             | Required | Default          | Description                       |
| ----------------------- | ---------------- | -------- | ---------------- | --------------------------------- |
| `drone_id`              | `int`            | Yes      | —                | Unique drone identifier (0-based) |
| `mavsdk_port`           | `int`            | No       | 14550            | gRPC port for MAVSDK autopilot    |
| `mavlink_port`          | `int`            | No       | 14540            | UDP port for MAVLink protocol     |
| `mqtt_broker_address`   | `str`            | No       | "localhost:1883" | MQTT broker (host:port)           |
| `sade_zone_config_path` | `Path \| None`   | No       | None             | Path to zone configuration        |
| `custom_settings`       | `dict[str, Any]` | No       | {}               | User-defined mission parameters   |

#### Methods

##### `model_dump() → dict[str, Any]`

Export configuration as dictionary.

```python
config_dict = config.model_dump()
```

##### `model_dump_json() → str`

Export configuration as JSON string.

```python
json_str = config.model_dump_json()
```

---

## ResilientDrone

Main interface for controlling drones and monitoring telemetry.

### Initialization

```python
from software_pilot.uav import ResilientDrone

drone = ResilientDrone(
    listen_port="14540",
    drone_id=0,
    mavsdk_port=14550,
    max_retries=10,
    retry_delay=5,
)
```

### Parameters

- `listen_port` (str): UDP port the drone listens on
- `drone_id` (int): Unique identifier for this drone
- `mavsdk_port` (int): gRPC port for local MAVSDK service
- `max_retries` (int): Maximum reconnection attempts (default: 10)
- `retry_delay` (int): Delay between retries in seconds (default: 5)
- `schema` (str): Connection schema (default: "udpin://")
- `host` (str): Host to connect to (default: "0.0.0.0")

### Connection

#### `async connect() → None`

Connect to the drone autopilot. Automatically retries on failure.

```python
try:
    await drone.connect()
except ConnectionError:
    print("Failed to connect after max retries")
```

**Raises:**

- `ConnectionError`: If unable to connect after `max_retries` attempts

#### `async ensure_connected() → None`

Ensure drone is connected, reconnecting if necessary.

```python
await drone.ensure_connected()
```

### Position and Telemetry

#### `async fetch_drone_position() → tuple[float, float, float]`

Get current drone position.

**Returns:** `(latitude, longitude, altitude_msl)`

```python
lat, lon, msl_alt = await drone.fetch_drone_position()
print(f"Position: {lat:.6f}, {lon:.6f}, altitude: {msl_alt:.1f}m")
```

#### `async wait_for_global_position_estimate() → None`

Wait until GPS has a valid position estimate.

```python
await drone.wait_for_global_position_estimate()
```

#### `async telemetry_position()`

Stream continuous position updates.

**Yields:** Position objects

```python
async for position in drone.telemetry_position():
    print(f"Lat: {position.latitude_deg}, Lon: {position.longitude_deg}")
    break  # Exit loop after first update
```

#### `async telemetry_health()`

Stream continuous health status.

**Yields:** Health status objects

```python
async for health in drone.telemetry_health():
    print(f"GPS OK: {health.is_global_position_ok}")
    break
```

### Basic Actions

#### `async action_arm() → None`

Arm the drone motors (prepare for takeoff).

```python
await drone.action_arm()
```

**May raise:**

- Connection errors if drone is unreachable

#### `async action_takeoff() → None`

Command the drone to take off to default altitude.

```python
await drone.action_takeoff()
```

#### `async action_land() → None`

Command the drone to land at current location.

```python
await drone.action_land()
```

### Mission Control

#### `async execute_mission(mission_steps: list[MissionStep]) -> None`

Upload and execute a mission.

```python
mission_steps = [
    MissionStep(...),
    MissionStep(...),
]
await drone.execute_mission(mission_steps)
```

**Parameters:**

- `mission_steps`: List of `MissionStep` objects defining the flight plan

**Behavior:**

1. Uploads all waypoints to autopilot
2. Arms drone
3. Starts mission
4. Monitors progress
5. Returns when complete

#### `async mission_upload_mission(mission_plan) → None`

Upload mission without starting execution.

```python
from mavsdk.mission import MissionPlan, MissionItem

items = [MissionItem(...)]
plan = MissionPlan(items)
await drone.mission_upload_mission(plan)
```

#### `async mission_start_mission() → None`

Start previously uploaded mission.

```python
await drone.mission_start_mission()
```

#### `async mission_mission_progress()`

Monitor mission execution progress.

**Yields:** Progress objects with `current` and `total` fields

```python
async for progress in drone.mission_mission_progress():
    print(f"Waypoint {progress.current}/{progress.total}")
```

### Internal Properties

#### `mission: Mission`

Direct access to MAVSDK `Mission` object for advanced operations.

```python
# Use MAVSDK API directly if needed
await drone.mission.clear_mission()
```

---

## Mission Planning

### `MissionStep`

Represents a single waypoint in a flight plan.

```python
from software_pilot.uav import MissionStep

step = MissionStep(
    short_name="waypoint_1",
    description="Fly north to search area",
    ned=NED(north=500, east=0, down=-100),
    home_alt=229.0,
    speed=15.0,
    home=home_lla,
)
```

#### Parameters

| Parameter     | Type    | Required | Description                         |
| ------------- | ------- | -------- | ----------------------------------- |
| `short_name`  | `str`   | Yes      | Brief identifier (used in logs)     |
| `description` | `str`   | Yes      | Human-readable description          |
| `ned`         | `NED`   | Yes      | Position relative to home           |
| `home_alt`    | `float` | Yes      | Sea-level altitude at home (meters) |
| `speed`       | `float` | Yes      | Flight speed (m/s)                  |
| `home`        | `Lla`   | Yes      | Home position (Lla object)          |

#### Methods

##### `create_mission_item() → MissionItem`

Convert to MAVSDK `MissionItem` for upload.

```python
item = step.create_mission_item()
```

### `NED`

North-East-Down coordinate system (relative to home).

```python
from software_pilot.uav import NED

ned = NED(
    north=100.0,    # meters north
    east=50.0,      # meters east
    down=-75.0,     # meters below (negative = up)
)
```

The `down` value is typically **negative** to indicate altitude above ground.

**Examples:**

```python
# 500m north, 0m east, 100m altitude above home
NED(north=500, east=0, down=-100)

# Directly above home at 50m
NED(north=0, east=0, down=-50)

# 200m southeast at 150m altitude
NED(north=0, east=200, down=-150)

# Return to home at same altitude
NED(north=0, east=0, down=0)
```

---

## SADE Zone Access

### `request_sade_zone_entry()`

Request airspace access for the drone to enter a SADE-controlled zone.

```python
from software_pilot.zones import request_sade_zone_entry

lease = request_sade_zone_entry(drone, emulate_wait=False)
if lease:
    print(f"Access granted until {lease.expiration_time}")
    # Safe to enter zone
else:
    print("Access denied, returning home")
```

#### Parameters

| Parameter      | Type             | Default | Description                                |
| -------------- | ---------------- | ------- | ------------------------------------------ |
| `drone`        | `ResilientDrone` | —       | The drone requesting access                |
| `emulate_wait` | `bool`           | False   | If true, sleep to simulate request latency |

#### Returns

- `SadeZoneLease` if access granted
- `None` if access denied or already occupied

### `SadeZoneLease`

Represents approval to operate in a zone.

```python
from software_pilot.zones import SadeZoneLease
from datetime import datetime, UTC

lease = SadeZoneLease(
    drone_id=0,
    zone_id="sade-zone-1",
    grant_time=datetime.now(UTC),
    expiration_time=datetime.now(UTC) + timedelta(minutes=5),
)
```

#### Attributes

| Attribute         | Type       | Description                |
| ----------------- | ---------- | -------------------------- |
| `drone_id`        | `int`      | Drone that holds the lease |
| `zone_id`         | `str`      | Zone identifier            |
| `grant_time`      | `datetime` | When lease was granted     |
| `expiration_time` | `datetime` | When lease expires         |

#### Methods

##### `is_active(now: datetime) -> bool`

Check if lease is still valid at given time.

```python
from datetime import datetime, UTC

if lease.is_active(datetime.now(UTC)):
    print("Safe to operate")
else:
    print("Lease expired, return home")
```

---

## Telemetry

### Async Streams

All telemetry methods return async generators. Use `async for` to consume:

```python
async for update in drone.telemetry_health():
    print(update)
    # Process one update, then exits (remove break to continue streaming)
    break
```

### Position Stream

```python
async for position in drone.telemetry_position():
    print(f"Lat: {position.latitude_deg}")
    print(f"Lon: {position.longitude_deg}")
    print(f"Alt (ABS): {position.absolute_altitude_m}")
    print(f"Alt (REL): {position.relative_altitude_m}")
```

### Health Stream

```python
async for health in drone.telemetry_health():
    print(f"GPS ready: {health.is_global_position_ok}")
    print(f"Compass ready: {health.is_magnetometer_ok}")
    print(f"Barometer ready: {health.is_barometer_ok}")
```

### Connection State Stream

```python
async for state in drone.core_connection_state():
    print(f"Connected: {state.is_connected}")
    print(f"UUID: {state.uuid}")
```

---

## Exceptions

### `ConnectionError`

Raised when unable to establish or maintain connection to drone.

```python
try:
    await drone.connect()
except ConnectionError as e:
    print(f"Connection failed: {e}")
```

### `MissionError` (MAVSDK)

Raised when mission upload or execution fails.

```python
from mavsdk.mission import MissionError

try:
    await drone.execute_mission(steps)
except MissionError as e:
    print(f"Mission error: {e}")
```

### `ValueError`

Raised when configuration validation fails.

```python
try:
    config = PilotConfig(drone_id=-1)  # Invalid
except ValueError as e:
    print(f"Configuration error: {e}")
```

---

## Complete Example

```python
import asyncio
from pathlib import Path
from droneresponse_mathtools import Lla
from software_pilot.config import PilotConfig
from software_pilot.uav import ResilientDrone, MissionStep, NED
from software_pilot.zones import request_sade_zone_entry


async def main():
    # Load configuration
    config = PilotConfig(
        drone_id=0,
        mavsdk_port=14550,
        custom_settings={"speed_mps": 15.0}
    )

    # Create drone interface
    drone = ResilientDrone(
        listen_port="14540",
        drone_id=config.drone_id,
        mavsdk_port=config.mavsdk_port,
    )

    try:
        # Connect
        await drone.connect()
        await drone.wait_for_global_position_estimate()

        # Get home position
        lat, lon, alt = await drone.fetch_drone_position()
        home = Lla(lat=lat, lon=lon, altitude=alt)

        # Create mission
        speed = config.custom_settings["speed_mps"]
        mission = [
            MissionStep(
                short_name="takeoff",
                description="Take off",
                ned=NED(north=0, east=0, down=-50),
                home_alt=home.altitude,
                speed=speed,
                home=home,
            ),
            MissionStep(
                short_name="search",
                description="Fly north to search area",
                ned=NED(north=500, east=0, down=-50),
                home_alt=home.altitude,
                speed=speed,
                home=home,
            ),
        ]

        # Request zone access if needed
        lease = request_sade_zone_entry(drone)
        if lease:
            print(f"Zone access granted until {lease.expiration_time}")

        # Execute mission
        await drone.execute_mission(mission)

        # Land
        await drone.action_land()

    except Exception as e:
        print(f"Mission failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## See Also

- [Configuration](CONFIG_PILOT_FORMAT.md) - How to configure pilots
- [Contributing](CONTRIBUTING.md) - How to contribute missions
- [Examples](examples/) - Example missions
- [Main README](README.md)
