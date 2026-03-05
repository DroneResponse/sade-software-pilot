# SADE Software Pilots

Customizable autonomous drone missions for SADE simulations.

- [SADE Software Pilots](#sade-software-pilots)
    - [Quick Start](#quick-start)
    - [What is a Software Pilot?](#what-is-a-software-pilot)
    - [Repository Structure](#repository-structure)
    - [API Quick Reference](#api-quick-reference)
        - [DroneOperations](#droneoperations)
        - [SADE Zone Access](#sade-zone-access)
        - [Configuration](#configuration)
    - [Documentation](#documentation)
    - [Support](#support)

## Quick Start

The high-level flow looks like this:

1. **Fork the repository** to your GitHub account; clone it locally
2. **Create a feature branch**: `git switch -c feature/my-mission`; feel free to
    name it something more descriptive.
3. **Edit mission logic**: Modify `src/software_pilot/mission.py`
4. **Test locally**: `just hooks` and `just test`
    This is highly recommended for reducing the feedback loop from minutes or hours (in
    case of human approval) to seconds. Write tests that cover your changes before
    running a simulation with them. See `tests/` for examples.
5. **Push and open a PR**: `git push origin feature/my-mission`; open a PR to
    `DroneResponse/sade-software-pilot` base repository, targeting
    `contrib/{username}/my-mission`
6. **Wait for approval**: SADE team reviews and merges to
    `contrib/{username}/my-mission`
7. **Run in SADE**: Configure a simulation in <https://sade.crc.nd.edu> pointing to the commit
    hash of your merged PR branch; then start the simulation.

Detailed instructions:

0. Fork this repository

    ```bash
    gh repo fork --default-branch-only DroneResponse/sade-software-pilot --clone=true
    # or manually fork on GitHub and clone it
    cd sade-software-pilot
    ```

1. Install `just` and `uv`

    ```bash
    cargo install just
    # OR
    curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/.local/bin
    ```

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # OR
    cargo install --locked uv
    ```

    Alternative installation methods at <https://docs.astral.sh/uv/getting-started/installation/>

2. Prepare the development environment

    ```bash
    just dev-setup
    ```

3. Customize your mission; see [`src/software_pilot/mission.py`](./src/software_pilot/mission.py).

    Skip this step if you just want to run the example mission as-is.

4. Test locally

    ```bash
    # run pre-commit hooks for static analysis, linting, formatting, etc.
    just hooks

    # run automated tests, so you don't need to wait minutes
    # for a simulation run to catch some bug categories
    just test
    ```

5. Use in SADE simulation.

    Once your code is ready, open a PR to our base repository. Please see
    [docs/contributing.md](docs/contributing.md) for more details.

6. Once merged, configure a simulation in <https://sade.crc.nd.edu> pointing to the
    commit hash of your merged PR branch; then start the simulation.

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
