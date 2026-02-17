# Contributing to SADE Software Pilots

Welcome! This guide explains how to fork, customize, and submit your custom software
pilot.

## Quick Start

```bash
# 1. Fork the repo on GitHub
# Navigate to https://github.com/DroneResponse/sade-software-pilot and click "Fork"

# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/sade-software-pilot.git
cd sade-software-pilot

# 3. Setup development environment
uv sync

# 4. Customize your mission
# edit the source files under src/software_pilot/

# 5. Test locally
just test

# 6. Push and open a PR
git push origin feature/my-mission
# Then open a PR at: https://github.com/DroneResponse/sade-software-pilot
```

## Detailed Workflow

### 1. Fork the Repository

On GitHub:

1. Navigate to
   [DroneResponse/sade-software-pilot](https://github.com/DroneResponse/sade-software-pilot)
2. Click the **Fork** button (top-right)
3. Choose your personal account as the fork destination

### 2. Clone Your Fork

```bash
git clone https://github.com/YOUR_USERNAME/sade-software-pilot.git
cd sade-software-pilot
```

Replace `YOUR_USERNAME` with your GitHub username.

### 3. Install Dependencies

Using `uv` (the recommended Python package manager):

```bash
uv sync
```

This creates a virtual environment with all dependencies installed.

### 4. Create a Feature Branch

```bash
git checkout -b feature/your-mission-name
```

**Naming convention:** `feature/` prefix for new missions, `fix/` for bug fixes

### 5. Customize Your Mission

Edit `src/software_pilot/mission.py` to implement your mission logic:

```python
async def run_example_mission(config: PilotConfig, drone: ResilientDrone) -> None:
    """Your custom mission implementation."""
    # Fetch drone position
    lat, lon, alt = await drone.fetch_drone_position()
    home = Lla(lat=lat, lon=lon, altitude=alt)

    # Create mission waypoints
    mission = [
        MissionStep(
            short_name="takeoff",
            description="Take off",
            ned=NED(north=0, east=0, down=-50),  # 50m altitude
            home_alt=home.altitude,
            speed=20.0,  # m/s
            home=home,
        ),
        # Add more waypoints...
    ]

    # Execute mission
    await drone.execute_mission(mission)

    # Request SADE zone access if needed
    lease = request_sade_zone_entry(drone, emulate_wait=False)
    if lease:
        print(f"Zone access granted until {lease.expiration_time}")

    # Land
    await drone.action_land()
```

### 6. Write Tests

Add tests for your mission in `tests/`:

```python
import pytest
from software_pilot.mission import create_example_mission
from droneresponse_mathtools import Lla

@pytest.mark.asyncio
async def test_mission_creation():
    home = Lla(lat=41.6, lon=-86.3, altitude=229)
    mission = await create_example_mission(home)
    assert len(mission) > 0
    assert mission[0].short_name == "takeoff"
```

Run tests:

```bash
uv run pytest tests/
```

### 7. Quality checks

Ensure code quality:

```bash
# Run linter, formatter, type checking, etc
just hooks
# useful, as sometimes these will catch bugs before running the code
```

### 8. Commit and Push

```bash
git add src/ tests/
git commit -m "Add search-pattern mission for autonomous grid search"
git push origin feature/your-mission-name
```

### 9. Open a Pull Request

On GitHub:

1. Navigate to your fork
2. Click **Pull Requests** → **New Pull Request**
3. Select:
   - **Base:** `main` (SADE original repository)
   - **Compare:** `feature/your-mission-name` (your fork)
4. Fill out the PR template.

### 10. Review Process

A SADE team member will:

- **Review** your mission logic, API usage, and code quality
- **Comment** on any questions or suggestions
- **Approve** once everything looks good
- **Merge** to a custom branch: `contrib/{username}/{mission-name}`

**What we look for:**

- ✅ Mission logic is sound (waypoints within bounds, realistic flight profiles)
- ✅ Correct use of SADE APIs (`ResilientDrone`, `request_sade_zone_entry()`)
- ✅ No security issues (safe file I/O, no shell invocation)
- ✅ Comprehensive tests (this will shorten the feedback loop for you, as it is faster to
  run tests than to submit a simulation)

### 11. Use Your Custom Pilot

Once approved and merged, reference your pilot in simulation configs:

```json
{
  "pilot": {
    "repo_url": "https://github.com/YOUR_USERNAME/sade-software-pilot",
    "repo_branch": "contrib/YOUR_USERNAME/mission-name",
    "custom_settings": {
      "grid_size_m": 100,
      "search_altitude_m": 150
    }
  },
  "drones": [ ... ],
  "environment": [ ... ]
}
```

## API Reference

### Core Classes

#### `ResilientDrone`

Main interface to drone operations.

**Methods:**

- `await drone.connect()` - Connect to autopilot
- `await drone.fetch_drone_position()` - Get lat/lon/alt
- `await drone.execute_mission(mission_steps)` - Upload and execute waypoints
- `await drone.action_arm()` - Arm the drone
- `await drone.action_takeoff()` - Take off
- `await drone.action_land()` - Land
- `await drone.telemetry_position()` - Stream live position
- `await drone.telemetry_health()` - Stream health status

#### `MissionStep`

Represents a single waypoint in a mission.

**Constructor:**

```python
MissionStep(
    short_name="waypoint_1",          # brief identifier
    description="fly north 100m",     # human-readable description
    ned=NED(north=100, east=0, down=-50),  # coordinates relative to home
    home_alt=229.0,                   # sea-level altitude of home
    speed=20.0,                       # m/s
    home=home_lla,                    # Lla object for home position
)
```

#### `NED`

North-East-Down coordinate system (relative to home position).

```python
NED(
    north=100,   # meters north of home
    east=50,     # meters east of home
    down=-100,   # meters below home (negative = up)
)
```

### SADE Zone Access

#### `request_sade_zone_entry(drone, emulate_wait=False)`

Request airspace access for a specific zone.

**Returns:** `SadeZoneLease` if approved, `None` if denied

**Example:**

```python
lease = request_sade_zone_entry(drone, emulate_wait=False)
if lease:
    print(f"Access granted until {lease.expiration_time}")
    # Now it's safe to enter the zone
else:
    print("Access denied, returning home")
    await drone.action_land()
```

### Configuration

#### `PilotConfig`

Configuration passed to your pilot at startup.

**Attributes:**

- `drone_id: int` - Unique drone identifier
- `mavsdk_port: int` - gRPC autopilot port
- `mavlink_port: int` - MAVLink UDP port
- `mqtt_broker_address: str` - MQTT broker for telemetry
- `sade_zone_config_path: Path | None` - Zone configuration file
- `custom_settings: dict[str, Any]` - User-provided settings

**Example:**

```python
async def run_mission(config: PilotConfig):
    print(f"Flying drone {config.drone_id}")
    print(f"Custom settings: {config.custom_settings}")
    speed = config.custom_settings.get("speed_mps", 15.0)
```

## Troubleshooting

### Dependency Conflicts

**Problem:** `uv sync` fails with dependency resolution error

**Solution:**

- Check that dependencies don't conflict with SADE core
- See `pyproject.toml` for current versions
- Propose version updates in your PR

### Import Errors

**Problem:** `ImportError: cannot import name 'ResilientDrone'`

**Solution:**

```bash
# Ensure package is installed in editable mode
uv sync

# Then run with uv
uv run python src/software_pilot/mission.py
```

### Autopilot Connection Fails

**Problem:** `ConnectionError: Could not connect to drone`

**Solution:**

- Verify MAVSDK port matches simulator configuration
- Check Firmware is running and listening
- Monitor logs: `docker compose logs sade-sim`

### Tests Don't Run

**Problem:** `ModuleNotFoundError` during pytest

**Solution:**

```bash
# Ensure tests can import your package
cd sade-software-pilot
uv run pytest tests/ -v
```

## Getting Help

- **API Questions:** See [API.md](API.md)
- **SADE Concepts:** See [QUICKSTART.md](QUICKSTART.md)
- **Examples:** Browse [examples/](examples/)
- **Issues:** Check [GitHub
  Issues](https://github.com/DroneResponse/sade-software-pilot/issues)
- **Questions:** Start a [GitHub
  Discussion](https://github.com/DroneResponse/sade-software-pilot/discussions)

## Code of Conduct

Be respectful, inclusive, and professional. We appreciate all contributions!

---

Happy flying! 🚁
