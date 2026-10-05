import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from unittest.mock import patch

from scripts.location import parse_bus_locations, parse_route_stations, should_refresh_route_stations
from scripts.realtime import get_realtime_data, parse_realtime_v2_data


FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class FakeResponse:
    def __init__(self, payload, is_json):
        self.payload = payload
        self.is_json = is_json

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    def raise_for_status(self):
        return None

    async def json(self):
        return self.payload

    async def text(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)


def test_v2_bus_arrival_keeps_existing_fields_and_adds_optional_details():
    now = datetime(2026, 10, 4, 1, 0, tzinfo=timezone.utc)

    snapshot = parse_realtime_v2_data(fixture("bus_realtime_v2.json"), 7001, [1001], now)

    assert snapshot.stop_id == 7001
    assert snapshot.route_ids == (1001,)
    assert snapshot.arrival_items == [{
        "route_id": 1001,
        "stop_id": 7001,
        "arrival_seq": 1,
        "remaining_stop_count": 3,
        "remaining_seat_count": 12,
        "remaining_time": timedelta(minutes=5),
        "low_plate": True,
        "current_stop_name": "한대앞역",
        "plate_no": "경기70아1234",
        "crowded": 2,
        "state_code": 2,
        "last_updated_time": now,
    }]


def test_v2_route_station_and_vehicle_location_fixtures_parse():
    now = datetime(2026, 10, 4, 1, 0, tzinfo=timezone.utc)

    assert parse_route_stations(fixture("bus_route_station_v2.json"), 1001, now) == [{
        "route_id": 1001,
        "station_seq": 1,
        "station_id": 200000001,
        "station_name": "한대앞역",
        "updated_at": now,
    }]
    location = parse_bus_locations(fixture("bus_location_v2.json"), 1001, now)[0]
    assert location["plate_no"] == "경기70아1234"
    assert location["crowded"] == 2
    assert location["remaining_seat_count"] == 12
    assert location["state_code"] == 2


def test_route_station_refresh_uses_a_24_hour_ttl():
    now = datetime(2026, 10, 4, 1, 0, tzinfo=timezone.utc)

    assert should_refresh_route_stations(None, now)
    assert not should_refresh_route_stations(now - timedelta(hours=23), now)
    assert should_refresh_route_stations(now - timedelta(hours=25), now)


def test_bus_v2_auth_error_falls_back_to_v1_fixture(monkeypatch):
    monkeypatch.setenv("BUS_API_KEY", "fixture-key")
    v1_xml = (FIXTURES / "bus_realtime_v1.xml").read_text()
    session = FakeSession([
        FakeResponse({"response": {"header": {"resultCode": "30"}, "body": {"items": []}}}, True),
        FakeResponse(v1_xml, False),
    ])

    with patch("scripts.realtime.ClientSession", return_value=session):
        snapshot = asyncio.run(get_realtime_data(7001, [1001]))

    assert len(session.calls) == 2
    assert snapshot.arrival_items[0]["remaining_stop_count"] == 3
    assert snapshot.arrival_items[0]["current_stop_name"] is None
