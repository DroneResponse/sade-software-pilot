"""Tests for software_pilot.zones module."""

from datetime import UTC
from datetime import datetime
from datetime import timedelta

from src.software_pilot.zones import SadeZoneLease


class TestSadeZoneLease:
    """Test SadeZoneLease dataclass."""

    def test_lease_creation(self) -> None:
        """Test creating a SadeZoneLease."""
        now = datetime.now(UTC)
        expiry = now + timedelta(minutes=5)
        lease = SadeZoneLease(
            drone_id=0,
            zone_id="sade-zone-1",
            grant_time=now,
            expiration_time=expiry,
        )
        assert lease.drone_id == 0
        assert lease.zone_id == "sade-zone-1"
        assert lease.grant_time == now
        assert lease.expiration_time == expiry

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

    def test_lease_is_not_active_before_grant(self) -> None:
        """Test that is_active() returns False before grant time."""
        now = datetime.now(UTC)
        grant = now + timedelta(minutes=1)
        expiry = now + timedelta(minutes=6)
        lease = SadeZoneLease(
            drone_id=0,
            zone_id="sade-zone-1",
            grant_time=grant,
            expiration_time=expiry,
        )
        assert lease.is_active(now) is False

    def test_lease_is_not_active_after_expiry(self) -> None:
        """Test that is_active() returns False after expiry."""
        now = datetime.now(UTC)
        grant = now - timedelta(minutes=6)
        expiry = now - timedelta(minutes=1)
        lease = SadeZoneLease(
            drone_id=0,
            zone_id="sade-zone-1",
            grant_time=grant,
            expiration_time=expiry,
        )
        assert lease.is_active(now) is False

    def test_lease_is_active_at_grant_boundary(self) -> None:
        """Test that is_active() returns True at grant time."""
        now = datetime.now(UTC)
        grant = now
        expiry = now + timedelta(minutes=5)
        lease = SadeZoneLease(
            drone_id=0,
            zone_id="sade-zone-1",
            grant_time=grant,
            expiration_time=expiry,
        )
        assert lease.is_active(now) is True

    def test_lease_is_not_active_at_expiry_boundary(self) -> None:
        """Test that is_active() returns False at expiration time."""
        now = datetime.now(UTC)
        grant = now - timedelta(minutes=5)
        expiry = now
        lease = SadeZoneLease(
            drone_id=0,
            zone_id="sade-zone-1",
            grant_time=grant,
            expiration_time=expiry,
        )
        assert lease.is_active(now) is False

    def test_lease_to_dict(self) -> None:
        """Test serializing lease to dict."""
        now = datetime.now(UTC)
        expiry = now + timedelta(minutes=5)
        lease = SadeZoneLease(
            drone_id=1,
            zone_id="sade-zone-2",
            grant_time=now,
            expiration_time=expiry,
        )
        data = lease.to_dict()
        assert data["drone_id"] == 1
        assert data["zone_id"] == "sade-zone-2"
        assert "grant_time" in data
        assert "expiration_time" in data

    def test_lease_from_dict(self) -> None:
        """Test constructing lease from dict."""
        now = datetime.now(UTC)
        expiry = now + timedelta(minutes=5)
        data = {
            "drone_id": 2,
            "zone_id": "sade-zone-3",
            "grant_time": now,
            "expiration_time": expiry,
        }
        lease = SadeZoneLease.from_dict(data)
        assert lease.drone_id == 2
        assert lease.zone_id == "sade-zone-3"
        assert lease.grant_time == now
        assert lease.expiration_time == expiry

    def test_lease_default_zone_id(self) -> None:
        """Test that zone_id defaults to 'sade-zone-1'."""
        now = datetime.now(UTC)
        expiry = now + timedelta(minutes=5)
        lease = SadeZoneLease(
            drone_id=0,
            grant_time=now,
            expiration_time=expiry,
        )
        assert lease.zone_id == "sade-zone-1"

    def test_lease_with_varying_durations(self) -> None:
        """Test leases with different durations."""
        now = datetime.now(UTC)

        # Short lease
        short_lease = SadeZoneLease(
            drone_id=0,
            grant_time=now,
            expiration_time=now + timedelta(seconds=30),
        )
        assert short_lease.is_active(now + timedelta(seconds=15))

        # Long lease
        long_lease = SadeZoneLease(
            drone_id=1,
            grant_time=now,
            expiration_time=now + timedelta(days=1),
        )
        assert long_lease.is_active(now + timedelta(hours=12))
