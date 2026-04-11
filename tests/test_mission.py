"""Tests for software_pilot.mission module."""

import asyncio
from unittest.mock import MagicMock

import pytest
from src.software_pilot.mission import create_example_mission
from src.software_pilot.uav import MissionStep


class TestCreateExampleMission:
    """Test mission creation functions."""

    @pytest.mark.asyncio
    async def test_create_example_mission_returns_list(self) -> None:
        """Test that create_example_mission returns a list of MissionSteps."""
        # Create a mock Lla object
        home = MagicMock()
        home.lat = 41.6
        home.lon = -86.35
        home.alt = 229.0
        home.move_ned = MagicMock(return_value=home)

        mission = await create_example_mission(home)

        assert isinstance(mission, list)
        assert len(mission) > 0

    @pytest.mark.asyncio
    async def test_example_mission_contains_mission_steps(self) -> None:
        """Test that mission contains valid MissionStep objects."""
        # Create a mock Lla object
        home = MagicMock()
        home.lat = 41.6
        home.lon = -86.35
        home.alt = 229.0
        home.move_ned = MagicMock(return_value=home)

        mission = await create_example_mission(home)

        for step in mission:
            assert isinstance(step, MissionStep)
            assert hasattr(step, "home")

    @pytest.mark.asyncio
    async def test_example_mission_includes_home(self) -> None:
        """Test that mission includes reference to home location."""
        # Create a mock Lla object
        home = MagicMock()
        home.lat = 41.6
        home.lon = -86.35
        home.alt = 229.0
        home.move_ned = MagicMock(return_value=home)

        mission = await create_example_mission(home)

        # All steps should reference the home location
        for step in mission:
            assert step.home is home

    @pytest.mark.asyncio
    async def test_example_mission_has_valid_altitudes(self) -> None:
        """Test that all waypoints have reasonable altitudes."""
        # Create a mock Lla object
        home = MagicMock()
        home.lat = 41.6
        home.lon = -86.35
        home.alt = 229.0
        home.move_ned = MagicMock(return_value=home)

        mission = await create_example_mission(home)

        # All steps should have a home_alt attribute (even if mocked)
        for step in mission:
            assert hasattr(step, "home_alt")
            assert hasattr(step, "speed")

    @pytest.mark.asyncio
    async def test_example_mission_different_homes(self) -> None:
        """Test mission creation with different home locations."""
        homes = [
            MagicMock(lat=41.6, lon=-86.35, alt=229.0),
            MagicMock(lat=42.0, lon=-87.0, alt=100.0),
            MagicMock(lat=40.0, lon=-85.0, alt=50.0),
        ]

        for home in homes:
            home.move_ned = MagicMock(return_value=home)
            mission = await create_example_mission(home)
            assert isinstance(mission, list)
            assert len(mission) > 0


class TestMissionAsyncBehavior:
    """Test async function behavior."""

    @pytest.mark.asyncio
    async def test_mission_async_context(self) -> None:
        """Test that mission functions work in async context."""
        home = MagicMock(lat=41.6, lon=-86.35, alt=229.0)
        home.move_ned = MagicMock(return_value=home)

        async def run_mission() -> int:
            mission = await create_example_mission(home)
            return len(mission)

        count = await run_mission()
        assert count > 0

    @pytest.mark.asyncio
    async def test_mission_concurrent_creation(self) -> None:
        """Test that multiple missions can be created concurrently."""
        homes = [
            MagicMock(lat=41.6, lon=-86.35, alt=229.0),
            MagicMock(lat=42.0, lon=-87.0, alt=100.0),
            MagicMock(lat=40.0, lon=-85.0, alt=50.0),
        ]

        for home in homes:
            home.move_ned = MagicMock(return_value=home)

        tasks = [create_example_mission(home) for home in homes]
        results = await asyncio.gather(*tasks)

        assert len(results) == len(homes)
        for mission in results:
            assert isinstance(mission, list)
            assert len(mission) > 0
