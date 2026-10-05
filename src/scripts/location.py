import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from aiohttp import ClientSession, ClientTimeout
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from models import BusLocation, BusRouteStation, BusRouteStop


BASE_URL = "https://apis.data.go.kr/6410000/busrouteservice/v2"
ROUTE_STATION_URL = f"{BASE_URL}/getBusRouteStationListv2"
BUS_LOCATION_URL = "https://apis.data.go.kr/6410000/buslocationservice/v2/getBusLocationListv2"
ROUTE_STATION_TTL = timedelta(hours=24)


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    response = payload.get("response", payload)
    header = response.get("header", response.get("msgHeader", {}))
    code = str(header.get("resultCode", "0"))
    if code not in {"0", "00"}:
        raise RuntimeError(f"GBIS v2 request failed ({code})")
    body = response.get("body", response.get("msgBody", {}))
    items = body.get("items", body.get("item", body.get("busRouteStationList", body.get("busLocationList", []))))
    if isinstance(items, dict):
        return [items]
    return items or []


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def should_refresh_route_stations(updated_at: datetime | None, now: datetime) -> bool:
    return updated_at is None or updated_at < now - ROUTE_STATION_TTL


def parse_route_stations(
    payload: dict[str, Any], route_id: int, now: datetime | None = None,
) -> list[dict[str, Any]]:
    updated_at = now or datetime.now(timezone.utc)
    stations = []
    for item in _items(payload):
        station_seq = _int(item.get("stationSeq"))
        station_id = _int(item.get("stationId"))
        name = item.get("stationName") or item.get("stationNm")
        if station_seq is None or station_id is None or not name:
            continue
        stations.append({
            "route_id": route_id,
            "station_seq": station_seq,
            "station_id": station_id,
            "station_name": str(name),
            "updated_at": updated_at,
        })
    return stations


def parse_bus_locations(
    payload: dict[str, Any], route_id: int, now: datetime | None = None,
) -> list[dict[str, Any]]:
    updated_at = now or datetime.now(timezone.utc)
    locations = []
    for item in _items(payload):
        plate_no = item.get("plateNo")
        station_seq = _int(item.get("stationSeq"))
        if not plate_no or station_seq is None:
            continue
        raw_time = item.get("lastUpdateTime") or item.get("lastUpdatedTime")
        last_updated_time = updated_at
        if raw_time:
            try:
                last_updated_time = datetime.fromisoformat(str(raw_time))
                if last_updated_time.tzinfo is None:
                    last_updated_time = last_updated_time.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        locations.append({
            "route_id": route_id,
            "plate_no": str(plate_no),
            "station_seq": station_seq,
            "station_id": _int(item.get("stationId")),
            "crowded": _int(item.get("crowded")),
            "remaining_seat_count": _int(item.get("remainSeatCnt")),
            "low_plate": bool(_int(item.get("lowPlate"))) if item.get("lowPlate") is not None else None,
            "state_code": _int(item.get("stateCd")),
            "last_updated_time": last_updated_time,
        })
    return locations


async def _get_json(session: ClientSession, url: str, route_id: int, api_key: str) -> dict[str, Any]:
    async with session.get(
        url,
        params={"serviceKey": api_key, "routeId": route_id, "format": "json"},
    ) as response:
        response.raise_for_status()
        return await response.json(content_type=None)


async def refresh_bus_route_data(db_session: Session, now: datetime | None = None) -> None:
    api_key = os.getenv("BUS_API_KEY")
    if not api_key:
        logging.warning("Skipping GBIS v2 route and location APIs because BUS_API_KEY is not set.")
        return
    current_time = now or datetime.now(timezone.utc)
    route_ids = [row[0] for row in db_session.query(BusRouteStop.route_id).distinct().all()]
    if not route_ids:
        return
    timeout = ClientTimeout(total=10.0)
    async with ClientSession(timeout=timeout) as session:
        for route_id in route_ids:
            try:
                latest_route_station = db_session.execute(
                    select(BusRouteStation.updated_at)
                    .where(BusRouteStation.route_id == route_id)
                    .order_by(BusRouteStation.updated_at.desc())
                    .limit(1)
                ).scalar_one_or_none()
                if should_refresh_route_stations(latest_route_station, current_time):
                    route_payload = await _get_json(session, ROUTE_STATION_URL, route_id, api_key)
                    route_stations = parse_route_stations(route_payload, route_id, current_time)
                    if route_stations:
                        statement = insert(BusRouteStation).values(route_stations)
                        statement = statement.on_conflict_do_update(
                            index_elements=["route_id", "station_seq"],
                            set_={
                                "station_id": statement.excluded.station_id,
                                "station_name": statement.excluded.station_name,
                                "updated_at": statement.excluded.updated_at,
                            },
                        )
                        db_session.execute(statement)

                location_payload = await _get_json(session, BUS_LOCATION_URL, route_id, api_key)
                locations = parse_bus_locations(location_payload, route_id, current_time)
                db_session.execute(delete(BusLocation).where(BusLocation.route_id == route_id))
                if locations:
                    db_session.execute(insert(BusLocation).values(locations))
            except Exception as error:  # noqa: BLE001 - one route cannot block other route snapshots
                logging.warning("Skipping bus route %s location refresh: %s", route_id, error)
