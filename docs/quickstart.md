# Getting Started with SADE Software Pilots

A step-by-step guide to creating and deploying your first custom drone mission.

+ [Getting Started with SADE Software Pilots](#getting-started-with-sade-software-pilots)
    + [Quick Start](#quick-start)
    + [Step-by-Step Guide](#step-by-step-guide)
        + [Step 1: Prerequisites](#step-1-prerequisites)
        + [Step 2: Fork and Clone](#step-2-fork-and-clone)
        + [Step 3: Set Up Development Environment](#step-3-set-up-development-environment)
        + [Step 4: Understand the Project Structure](#step-4-understand-the-project-structure)
        + [Step 5: Customize Your Mission](#step-5-customize-your-mission)
        + [Step 6: Test Your Changes](#step-6-test-your-changes)
        + [Step 7: Commit and Push](#step-7-commit-and-push)
        + [Step 8: Open a Pull Request](#step-8-open-a-pull-request)
        + [Step 9: Deploy Your Mission](#step-9-deploy-your-mission)
    + [Common Customizations](#common-customizations)
        + [Change Drone Speed](#change-drone-speed)
        + [Add Custom Parameters](#add-custom-parameters)
        + [Request SADE Zone Access](#request-sade-zone-access)
        + [Monitor Drone Position](#monitor-drone-position)
    + [Troubleshooting](#troubleshooting)
    + [Next Steps](#next-steps)
    + [File Structure You'll Edit](#file-structure-youll-edit)
    + [Resources](#resources)
    + [Getting Help](#getting-help)

## Quick Start

```bash
# 1. Fork the repository
# Go to https://github.com/DroneResponse/sade-software-pilot and click "Fork"

# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/sade-software-pilot.git
cd sade-software-pilot

# 3. Install dependencies
uv sync

# 4. Test the default mission
uv run software-pilot --drone-id=0 --help

# 5. You're ready to customize!
```

## Step-by-Step Guide

### Step 1: Prerequisites

You'll need:

+ **Git** - Version control
+ **uv** - Python package and project manager <https://docs.astral.sh/uv/getting-started/installation/>
+ **just** - Task runner <https://github.com/casey/just>
+ **GitHub account** - To fork the repository

### Step 2: Fork and Clone

On GitHub:

1. Navigate to [DroneResponse/sade-software-pilot](https://github.com/DroneResponse/sade-software-pilot)
2. Click **Fork** (top-right corner)
3. Clone your fork:

```bash
git clone https://github.com/YOUR_USERNAME/sade-software-pilot.git
cd sade-software-pilot
```

### Step 3: Set Up Development Environment

Install dependencies:

```bash
uv sync
```

This creates a Python virtual environment with all dependencies installed.

Verify the installation:

```bash
uv run software-pilot --version
uv run software-pilot --help
```

You should see the CLI help text.

### Step 4: Understand the Project Structure

```
src/software_pilot/
  cli.py           # Entry point (CLI)
  config.py        # Configuration schema
  mission.py       # Edit here for your mission logic
  uav.py           # Drone control (don't modify)
  zones.py         # SADE zone access (don't modify)

examples/
  simple_waypoint_mission.py      # Reference
  sade_zone_aware_mission.py      # Reference

tests/
  test_mission.py  # Add tests here
```

### Step 5: Customize Your Mission

Open `src/software_pilot/mission.py` and edit the `run_example_mission()` function:

```python
async def run_example_mission(config: PilotConfig, drone: ResilientDrone) -> None:
    """Your custom mission. Called when the pilot starts."""

    # YOUR CODE HERE
    log.info(f"Flying drone {config.drone_id}")
```

**Example 1: Simple takeoff and land**

```python
async def run_example_mission(config: PilotConfig, drone: ResilientDrone) -> None:
    await drone.connect()
    await drone.wait_for_global_position_estimate()

    lat, lon, alt = await drone.fetch_drone_position()
    home = Lla(lat=lat, lon=lon, altitude=alt)

    # Take off to 50m
    await drone.action_takeoff()

    # Wait 5 seconds
    await asyncio.sleep(5)

    # Land
    await drone.action_land()
```

**Example 2: Fly a square pattern**

```python
async def run_example_mission(config: PilotConfig, drone: ResilientDrone) -> None:
    await drone.connect()
    await drone.wait_for_global_position_estimate()

    lat, lon, alt = await drone.fetch_drone_position()
    home = Lla(lat=lat, lon=lon, altitude=alt)

    altitude = 50.0
    leg = 200.0  # 200m per leg

    mission = [
        MissionStep(
            short_name="takeoff",
            description="Takeoff",
            ned=NED(north=0, east=0, down=-altitude),
            home_alt=home.altitude,
            speed=15.0,
            home=home,
        ),
        MissionStep(
            short_name="leg1",
            description="North",
            ned=NED(north=leg, east=0, down=-altitude),
            home_alt=home.altitude,
            speed=15.0,
            home=home,
        ),
        MissionStep(
            short_name="leg2",
            description="East",
            ned=NED(north=leg, east=leg, down=-altitude),
            home_alt=home.altitude,
            speed=15.0,
            home=home,
        ),
        MissionStep(
            short_name="leg3",
            description="South",
            ned=NED(north=0, east=leg, down=-altitude),
            home_alt=home.altitude,
            speed=15.0,
            home=home,
        ),
        MissionStep(
            short_name="home",
            description="Return home",
            ned=NED(north=0, east=0, down=-altitude),
            home_alt=home.altitude,
            speed=15.0,
            home=home,
        ),
    ]

    await drone.execute_mission(mission)
    await drone.action_land()
```

### Step 6: Test Your Changes

Run tests (if any):

```bash
uv run pytest tests/
```

Check code quality:

```bash
uv run ruff check src/
uv run mypy src/
```

### Step 7: Commit and Push

```bash
git add src/
git commit -m "feat: add custom search pattern mission"
git push origin feature/my-mission
```

### Step 8: Open a Pull Request

On GitHub:

1. Go to your fork
2. Click **Pull Requests** → **New Pull Request**
3. Describe your mission
4. Click **Create Pull Request**

A SADE team member will review and merge to a custom branch like `contrib/YOUR_USERNAME/my-mission`.

### Step 9: Deploy Your Mission

Once approved, use in simulations:

```json
{
  "pilot": {
    "repo_url": "https://github.com/YOUR_USERNAME/sade-software-pilot",
    "repo_branch": "contrib/YOUR_USERNAME/my-mission"
  },
  "drones": [ ... ],
  "environment": [ ... ]
}
```

## Common Customizations

### Change Drone Speed

```python
speed_mps = 20.0  # meters per second

mission = [
    MissionStep(
        ...
        speed=speed_mps,
        ...
    ),
]
```

### Add Custom Parameters

Users can pass custom settings via simulation config:

```json
{
  "pilot": {
    "custom_settings": {
      "search_grid_size": 100,
      "altitude": 150
    }
  }
}
```

Access them in your mission:

```python
def run_example_mission(config: PilotConfig, drone: ResilientDrone) -> None:
    grid_size = config.custom_settings.get("search_grid_size", 50)
    altitude = config.custom_settings.get("altitude", 100)
    log.info(f"Flying grid of {grid_size}m at {altitude}m altitude")
```

### Request SADE Zone Access

```python
from software_pilot.zones import request_sade_zone_entry

# Before entering a zone, request access
lease = request_sade_zone_entry(drone)

if lease:
    log.info(f"Zone access granted until {lease.expiration_time}")
    # Fly into the zone
else:
    log.warning("Zone access denied, returning home")
    # Return home
```

### Monitor Drone Position

```python
# Get single position update
lat, lon, msl_alt = await drone.fetch_drone_position()
print(f"Position: {lat:.6f}, {lon:.6f}, altitude: {msl_alt:.1f}m")

# Stream continuous updates
async for position in drone.telemetry_position():
    print(f"Lat: {position.latitude_deg}")
    break  # Exit after first update
```

## Troubleshooting

See [troubleshooting.md](TROUBLESHOOTING.md) for common issues and solutions.

## Next Steps

1. **Explore examples:** Browse [examples/](examples/)
2. **Read API docs:** See [API.md](API.md)
3. **Check CONTRIBUTING guide:** See [CONTRIBUTING.md](CONTRIBUTING.md)
4. **View configuration options:** See [CONFIG_PILOT_FORMAT.md](../../../CONFIG_PILOT_FORMAT.md)

## File Structure You'll Edit

```
src/software_pilot/
    mission.py              # EDIT: Your custom mission

    # avoid modifying:
    __init__.py
    cli.py
    config.py
    uav.py
    zones.py

tests/
    test_mission.py         # EDIT: Add tests for your mission

pyproject.toml            # EDIT: Change version, add dependencies
```

## Resources

+ **MAVSDK Documentation:** [MAVSDK Python](https://mavsdk.mavlink.io/)
+ **Coordinate System:** [NED Coordinates Explained](https://en.wikipedia.org/wiki/Local_tangent_plane_coordinates)
+ **SADE Overview:** See main [README.md](../README.md)
+ **API Reference:** See [API.md](api.md)

## Getting Help

+ Check [FAQ.md](faq.md)
+ Search [GitHub Issues](https://github.com/DroneResponse/sade-software-pilot/issues)
+ Start a [GitHub Discussion](https://github.com/DroneResponse/sade-software-pilot/discussions)
+ Contact SADE team

---

**Ready to fly?** Edit [mission.py](src/software_pilot/mission.py) and start coding! 🚁
