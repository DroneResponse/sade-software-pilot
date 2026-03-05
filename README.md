# SADE Software Pilots

Customizable autonomous drone missions for SADE simulations.

## Quick Start

### Install `just`

```bash
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/.local/bin
```

```bash
# Clone this repository
git clone https://github.com/DroneResponse/sade-software-pilot.git
cd sade-software-pilot

# Install dependencies
uv sync

# Customize your mission; see:
# src/software_pilot/mission.py

# Test locally
just test

# Use in SADE simulation
sade_wr submit --sim-config my-config.json
```

## What is a Software Pilot?

A software pilot is a Python package that contains autonomous mission logic for
simulated drones in SADE. Each pilot:

- Communicates with drone autopilots via MAVSDK
- Requests airspace access via SADE zone management
- Executes waypoint missions
- Can access custom configuration parameters

## Repository Structure

```text
src/software_pilot/
  __init__.py           # Package initialization
  cli.py                # Command-line interface
  config.py             # Configuration schema (Pydantic)
  mission.py            # Example mission implementation
  uav.py                # ResilientDrone wrapper for MAVSDK
  zones.py              # SADE zone access control

tests/
  test_mission.py       # Example tes     simple_waypoint_mission.py
  sade_zone_aware_mission.py
  search_pattern_mission.py

.github/workflows/
  pr-checks.yml         # Automated linting and testing
```

## Usage

### As the Template Repository

Start with the [official
template](https://github.com/DroneResponse/sade-software-pilot.git).

### 2. Customize for Your Mission

1. **Fork the repository** to your GitHub account
2. **Create a feature branch**: `git switch -c feature/my-mission`
3. **Edit mission logic**: Modify `src/software_pilot/mission.py`
4. **Test locally**: `just test`
5. **Push and open a PR**: `git push origin feature/my-mission`
6. **Wait for approval**: SADE team reviews and merges to
   `contrib/{username}/my-mission`

### 3. Run checks

```bash
# run tests to make sure your code works as expected before having to start a simulation run
just test

# linting, formatting, type checking, etc.
just hooks
```

### 4. Submitting your software pilot

When it looks good, you can open a PR to our base repository. Please see
[docs/contributing.md](docs/contributing.md) for more details.

## API Quick Reference

### DroneOperations

```python
from software_pilot.uav import ResilientDrone, MissionStep, NED
from droneresponse_mathtools import Lla

# Connect to autopilot
drone = ResilientDrone(
    listen_port="14540",
    drone_id=0,
    mavsdk_port=14550,
)
await drone.connect()

# Get current position
lat, lon, alt = await drone.fetch_drone_position()
home = Lla(lat=lat, lon=lon, altitude=alt)

# Create waypoints
mission = [
    MissionStep(
        short_name="takeoff",
        description="Take off",
        ned=NED(north=0, east=0, down=-50),
        home_alt=home.altitude,
        speed=20.0,
        home=home,
    ),
]

# Execute mission
await drone.execute_mission(mission)
await drone.action_land()
```

### SADE Zone Access

```python
from software_pilot.zones import request_sade_zone_entry

# Request access to a zone
lease = request_sade_zone_entry(drone, emulate_wait=False)
if lease:
    print(f"Zone access approved until {lease.expiration_time}")
else:
    print("Zone access denied")
```

### Configuration

```python
from software_pilot.config import PilotConfig

config = PilotConfig(
    drone_id=0,
    mavsdk_port=14550,
    custom_settings={"speed_mps": 15.0}
)
print(f"Flying drone {config.drone_id} at {config.custom_settings['speed_mps']} m/s")
```

## Documentation

- [API Reference](docs/api.md) - Complete API documentation
- [Contributing Guide](docs/contributing.md) - How to contribute missions
- [Quickstart](docs/quickstart.md) - Step-by-step getting started guide
- [Examples](examples/) - Example missions

## Support

- [API Documentation](docs/api.md)
- [FAQ](docs/faq.md)
- [Report Issues](https://github.com/DroneResponse/sade-software-pilot/issues)
- [Discussions](https://github.com/DroneResponse/sade-software-pilot/discussions)

---

**Ready to build your custom mission?** Start with the [Quickstart
Guide](docs/quickstart.md)!
