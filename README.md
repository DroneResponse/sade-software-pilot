# SADE Software Pilots

Customizable autonomous drone missions for SADE simulations.

## Quick Start

```bash
# Clone this repository
git clone https://github.com/DroneResponse/sade-software-pilot.git
cd sade-software-pilot

# Install dependencies
uv sync

# Customize your mission
nano src/software_pilot/mission.py

# Test locally
uv run pytest tests/

# Use in SADE simulation
sade_wr submit --sim-config my-config.json
```

## What is a Software Pilot?

A software pilot is a Python package that contains autonomous mission logic for simulated drones in SADE. Each pilot:

- Communicates with drone autopilots via MAVSDK
- Requests airspace access via SADE zone management
- Executes waypoint missions
- Can access custom configuration parameters

## Features

- 🚁 **MAVLink autopilot control** via MAVSDK
- 📍 **SADE zone-aware** airspace access requests
- 🔧 **Fully customizable** mission logic
- 📦 **Python package** distribution via git
- 🧪 **Built-in testing** support
- 📖 **Comprehensive API** documentation

## Repository Structure

```
src/software_pilot/
  __init__.py           # Package initialization
  cli.py                # Command-line interface
  config.py             # Configuration schema (Pydantic)
  mission.py            # Example mission implementation
  uav.py                # ResilientDrone wrapper for MAVSDK
  zones.py              # SADE zone access control

tests/
  test_mission.py       # Example tests

examples/
  simple_waypoint_mission.py
  sade_zone_aware_mission.py
  search_pattern_mission.py

.github/workflows/
  pr-checks.yml         # Automated linting and testing
```

## Usage

### As the Template Repository

Start with the official template:

```json
{
  "pilot": {
    "repo_url": "https://github.com/DroneResponse/sade-software-pilot.git",
    "repo_branch": "master"
  },
  "drones": [ ... ],
  "environment": [ ... ]
}
```

### Customize for Your Mission

1. **Fork the repository** to your GitHub account
2. **Create a feature branch**: `git checkout -b feature/my-mission`
3. **Edit mission logic**: Modify `src/software_pilot/mission.py`
4. **Test locally**: `uv run pytest tests/`
5. **Push and open a PR**: `git push origin feature/my-mission`
6. **Wait for approval**: SADE team reviews and merges to `contrib/{username}/my-mission`

Then use your custom pilot:

```json
{
  "pilot": {
    "repo_url": "https://github.com/YOUR_USERNAME/sade-software-pilot.git",
    "repo_branch": "contrib/YOUR_USERNAME/my-mission"
  }
}
```

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

- [API Reference](API.md) - Complete API documentation
- [Contributing Guide](CONTRIBUTING.md) - How to contribute missions
- [Configuration Format](CONFIG_PILOT_FORMAT.md) - Pilot configuration schema
- [Quickstart](QUICKSTART.md) - Step-by-step getting started guide
- [Examples](examples/) - Example missions

## Development

### Setup

```bash
uv sync
```

### Run Tests

```bash
uv run pytest tests/ -v
```

### Lint and Format

```bash
uv run ruff check src/ tests/      # Check
uv run ruff format src/ tests/     # Auto-format
uv run mypy src/                   # Type check
```

### Building

```bash
uv build              # Build package
uv pip install -e .   # Install editable
```

## Requirements

- Python 3.11+
- MAVSDK 3.10+
- MAVLink-compatible autopilot (PX4, ArduPilot, etc.)

## Dependencies

See [pyproject.toml](pyproject.toml) for complete list:

- `mavsdk` - Autopilot communication
- `pydantic` - Configuration validation
- `loguru` - Structured logging
- `droneresponse-mathtools` - Coordinate transformations
- `paho-mqtt` - MQTT telemetry (optional)

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:

- How to fork and customize
- Pull request process
- Code style guide
- Testing requirements

## License

See LICENSE file for details.

## Support

- 📖 [API Documentation](API.md)
- ❓ [FAQ](FAQ.md)
- 🐛 [Report Issues](https://github.com/DroneResponse/sade-software-pilot/issues)
- 💬 [Discussions](https://github.com/DroneResponse/sade-software-pilot/discussions)

---

**Ready to build your custom mission?** Start with the [Quickstart Guide](QUICKSTART.md)!
