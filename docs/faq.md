# FAQ: SADE Software Pilots

## General Questions

### What is a Software Pilot?

A software pilot is a Python package containing autonomous mission logic for simulated
drones. It communicates with drone autopilots via MAVSDK and can request airspace access
through SADE zone management.

### Do I need to be a Python expert?

No! Basic Python knowledge is sufficient. We provide examples, templates, and API
documentation. Most missions are simple: define waypoints, execute, land.

### Can I use external Python libraries?

Yes! Add them to `pyproject.toml` dependencies. Common choices:

- `numpy` for numerical calculations
- `scipy` for signal processing
- `requests` for HTTP calls

Just note: dependencies must be compatible with SADE core packages. Check dependency
conflicts before submitting PRs.

### Is the pilot sandboxed?

**Currently:** No, pilots run with autopilot process privileges. Security relies on code
review.

**Phase 2:** We'll add seccomp profiles and resource limits. See
[SECURITY.md](SECURITY.md).

## Development Questions

### How do I customize my mission?

Edit `src/software_pilot/mission.py` and edit `run_example_mission()`:

```python
async def run_example_mission(config: PilotConfig, drone: ResilientDrone) -> None:
    # Your code here
```

### Can I have multiple mission implementations?

Yes! Create new functions and import them in `mission.py`:

```python
async def run_example_mission(...):
    if config.custom_settings.get("mission_type") == "search":
        await my_search_mission(drone)
    elif config.custom_settings.get("mission_type") == "patrol":
        await my_patrol_mission(drone)
```

### How do I pass configuration to my mission?

Via `custom_settings` in simulation config:

```json
{
  "pilot": {
    "custom_settings": {
      "speed_mps": 20,
      "altitude": 150,
      "grid_size": 100
    }
  }
}
```

Access in mission:

```python
speed = config.custom_settings.get("speed_mps", 15)
```

### How do I handle mission failures?

Use try/except and log errors:

```python
try:
    await drone.execute_mission(mission)
except Exception as e:
    log.error(f"Mission failed: {e}")
    await drone.action_land()  # Safe fallback
```

## Testing Questions

### How do I test without SADE?

Mock the drone if you have pytest-asyncio:

```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_my_mission():
    drone = AsyncMock()
    config = PilotConfig(drone_id=0)

    # Your test
    await your_mission(config, drone)

    drone.execute_mission.assert_called()
```

### Do my tests run automatically?

Yes! PR checks run `uv run pytest` automatically. Failing tests block merge.

## Deployment Questions

### When does my pilot get used?

When the simulation config references it:

```json
{
  "pilot": {
    "repo_url": "https://github.com/YOUR_USERNAME/sade-software-pilot",
    "repo_branch": "contrib/YOUR_USERNAME/my-mission"
  }
}
```

### How long does deployment take?

- Repo clone: ~10 seconds
- Package install: ~30 seconds
- Drone initialization: ~5 seconds
- **Total: ~45 seconds before mission starts**

### Can I use SSH URLs for private repos?

Yes, but you need GitHub SSH credentials available during Docker build. Contact SADE
team for SSH key setup.

### What if my mission pulls the wrong branch?

The `repo_branch` field specifies exactly which branch. Double-check simulation config
before submitting.

## Troubleshooting Questions

### "ConnectionError: Could not connect to drone"

Usual causes:

1. **Autopilot not running** - Start PX4 simulator first
2. **Wrong port** - Check `mavsdk_port` in config
3. **Network isolated** - Verify Docker networking

**Fix:**

```bash
# Check MAVSDK is listening
docker exec sade-sim lsof -i :14550

# Restart container
docker compose restart sade-sim
```

### "ImportError: cannot import name 'ResilientDrone'"

Ensure you're using `uv run`:

```bash
# ✅ Correct
uv run python my_script.py

# ❌ Wrong
python my_script.py
```

The package must be installed in the virtual environment.

### "Tests fail locally but pass on PR"

Likely causes:

1. **Different Python version** - Use Python 3.14+
2. **Missing dependencies** - Run `uv sync` after pulling
3. **File paths** - Use relative paths, not absolute

**Fix:**

```bash
uv sync --refresh
uv run pytest tests/ -vv
```

### "Linter says X is wrong but it works"

Our CI requires passing all checks:

- `just hooks` runs pre-commit hooks locally.

Fix them before merging. Note formatters will change files automatically if needed; just
stage your changes and commit them.

Some problems cannot be automatically fixed and will need manual code changes or
explicit ignores at the line or file level.

## Mission Design Questions

### How fast can the drone go?

Typical speeds:

- Slow (search): 5-10 m/s
- Normal: 12-20 m/s
- Fast: 20-30 m/s

Simulator defaults to 20 m/s. Check PX4 documentation for autopilot limits.

### Can I fly at different altitudes?

Yes! Each waypoint gets its own altitude:

```python
mission = [
    MissionStep(..., ned=NED(..., down=-50), ...),   # 50m
    MissionStep(..., ned=NED(..., down=-100), ...),  # 100m
    MissionStep(..., ned=NED(..., down=-75), ...),   # 75m
]
```

### How do I calculate waypoint distances?

Use NED (North-East-Down) coordinates relative to home:

```python
# Home position (0, 0)
# North: positive north value
# East: positive east value
# Down: negative value (up from home)

NED(north=500, east=0, down=-100)    # 500m north, 100m altitude
NED(north=250, east=250, down=-100)  # 250m NE diagonal, 100m altitude
NED(north=0, east=0, down=0)         # Home at same altitude
```

### How long does a mission take?

**Formula:** `distance_traveled / speed_m_s + margin`

Example: 2000m total distance at 15 m/s ≈ 133 seconds ≈ 2 minutes

### Can missions interact with each other?

Yes, via MQTT or files, but it's advanced. See examples and API docs.

## Git/PR Questions

### I messed up a commit. How do I fix it?

Reset and recommit:

```bash
git reset --soft HEAD~1  # Undo last commit, keep changes
git add .
git commit -m "Fixed message"
git push --force origin my-branch
```

### How do I sync with upstream?

```bash
git remote add upstream https://github.com/DroneResponse/sade-software-pilot.git
git fetch upstream
git rebase upstream/master
git push origin --force my-branch
```

### My PR got feedback. How do I update it?

Make changes, commit, and push:

```bash
git add .
git commit -m "Address review feedback"
git push origin my-branch
```

GitHub automatically updates the PR.

### Can I have multiple PRs open?

Yes! Use separate branches:

```bash
git checkout -b feature/mission-1
# ... work ...
git push origin feature/mission-1

git checkout -b feature/mission-2
# ... work ...
git push origin feature/mission-2
```

## Contributing Questions

### Can I contribute non-mission code?

Maybe! Open an issue first to discuss:

- Bug fixes (usually welcome)
- New CLI features (discuss with SADE team)
- Refactoring (most welcome)

### How long does review take?

Typically 1-3 business days. Complex missions may take longer.

### What if my PR gets rejected?

No problem! We'll provide feedback to help. You can:

1. Update your PR with changes
2. Try a different approach
3. Open a discussion to brainstorm

### Can I be a maintainer?

Talk to the SADE team if you're interested in becoming an active contributor!

---

Still have questions? Open a [GitHub
Discussion](https://github.com/DroneResponse/sade-software-pilot/discussions)!
