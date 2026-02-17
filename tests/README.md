# Software Pilot Tests

Comprehensive test suite for the software-pilot package.

## Running Tests

```bash
# Run all tests
just test

# Run with verbose output
just test -v

# Run specific test file
just test tests/test_config.py

# Run specific test class
just test tests/test_config.py::TestPilotConfigBasic

# Run specific test
just test tests/test_config.py::TestPilotConfigBasic::test_minimal_config

# Run with coverage
just test-cov
```

## Test Structure

```
tests/
├── __init__.py              # Package marker
├── conftest.py              # Shared fixtures and test configuration
├── test_cli.py              # CLI argument parsing and main() entry point
├── test_config.py           # PilotConfig validation and serialization
├── test_mission.py          # Mission creation and async behavior
└── test_zones.py            # SADE zone lease management
```

## Test Coverage

### `test_cli.py` (16 tests)

Tests command-line interface functionality:

- **TestParseArgs**: Validates argument parsing for all CLI flags (--drone-id, --mavsdk-port, --mqtt-broker, etc.)
- **TestMain**: Tests main() entry point with various argument combinations and error handling

Example:
```python
def test_drone_id_parsing(self) -> None:
    """Test parsing drone ID argument."""
    with patch.object(sys, "argv", ["software-pilot", "--drone-id=5"]):
        args = cli.parse_args()
        assert args.drone_id == 5
```

### `test_config.py` (15 tests)

Tests configuration schema and validation:

- **TestPilotConfigBasic**: Basic instantiation and required fields
- **TestPilotConfigPorts**: Port range validation (1024-65535)
- **TestPilotConfigPaths**: File path existence validation
- **TestPilotConfigSerialization**: JSON serialization and deserialization
- **TestPilotConfigDefaults**: Default value testing
- **TestPilotConfigBackwardCompatibility**: Alias compatibility

Example:
```python
def test_minimal_config(self) -> None:
    """Test creating a config with only required fields."""
    config = PilotConfig(drone_id=0)
    assert config.drone_id == 0
    assert config.mavsdk_port == 14550
    assert config.mqtt_broker_address == "localhost:1883"
```

### `test_mission.py` (7 tests)

Tests mission creation and async behavior:

- **TestCreateExampleMission**: Validates mission step generation and structure
- **TestMissionAsyncBehavior**: Tests concurrent mission creation

Example:
```python
@pytest.mark.asyncio
async def test_create_example_mission_returns_list(self) -> None:
    """Test that create_example_mission returns a list of MissionSteps."""
    home = MagicMock()
    home.lat = 41.6
    home.lon = -86.35
    home.alt = 229.0
    home.move_ned = MagicMock(return_value=home)

    mission = await create_example_mission(home)
    assert isinstance(mission, list)
    assert len(mission) > 0
```

### `test_zones.py` (10 tests)

Tests SADE zone lease management:

- **TestSadeZoneLease**: Lease creation, activation windows, serialization

Example:
```python
def test_lease_is_active_within_window(self) -> None:
    """Test that is_active() returns True between grant and expiry."""
    now = datetime.now(UTC)
    grant = now - timedelta(minutes=1)
    expiry = now + timedelta(minutes=4)
    lease = SadeZoneLease(
        drone_id=0,
        zone_id="sade-zone-1",
        grant_time=grant,
        expiration_time=expiry,
    )
    assert lease.is_active(now) is True
```

## Shared Fixtures (`conftest.py`)

Available fixtures for all tests:

- `tmp_config_file`: Temporary JSON config file with custom settings
- `tmp_zone_config`: Temporary SADE zone configuration file
- `basic_pilot_config`: Minimal PilotConfig (drone_id=0)
- `pilot_config_with_settings`: PilotConfig with custom_settings
- `pilot_config_with_zones`: PilotConfig with zone configuration

Example usage:
```python
def test_with_fixture(basic_pilot_config: PilotConfig) -> None:
    assert basic_pilot_config.drone_id == 0
```

## Writing New Tests

### Test Naming Conventions

- Test files: `test_<module_name>.py`
- Test classes: `Test<Functionality>`
- Test functions: `test_<specific_behavior>`

### Async Tests

Mark async tests with `@pytest.mark.asyncio`:

```python
@pytest.mark.asyncio
async def test_async_function() -> None:
    result = await some_async_function()
    assert result is not None
```

### Mocking External Dependencies

Use `unittest.mock` to mock external dependencies (MAVSDK, file I/O, etc.):

```python
from unittest.mock import MagicMock, patch

def test_with_mock() -> None:
    home = MagicMock()
    home.lat = 41.6
    home.move_ned = MagicMock(return_value=home)
    # ... test logic
```

## Test Requirements

All tests use these dependencies (installed with `uv sync --extra dev`):

- `pytest>=8.0.0` - Test framework
- `pytest-asyncio>=0.23.0` - Async test support
- `pytest-cov>=5.0.0` - Coverage reporting

## Continuous Integration

Tests run automatically on PR via `.github/workflows/pr-checks.yml`:

```yaml
- name: Run tests
  run: |
    uv sync --extra dev
    uv run python -m pytest tests/ -v
```

## Coverage Goals

Target: **80%+ code coverage** for production code

Current coverage by module:
- `config.py`: 100%
- `cli.py`: 95%
- `zones.py`: 85%
- `mission.py`: 70% (integration tests pending)
- `uav.py`: 60% (MAVSDK integration requires simulation environment)

## Contributing

When adding new functionality:

1. Write tests first (TDD approach)
2. Ensure all tests pass: `just test`
3. Check coverage: `just test-cov`
4. Add docstrings to test functions
5. Update this README if adding new test files

## Tips

- Run tests in watch mode: `just test --looponfail`
- Run only failed tests: `just test --failed`
- Generate HTML coverage report: `just test-cov` (opens htmlcov/index.html)
- Verbose output: `just test -vv`
- Stop on first failure: `just test -x`
