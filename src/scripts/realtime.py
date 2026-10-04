import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from aiohttp import ClientTimeout, ClientSession
from bs4 import BeautifulSoup, Tag


@dataclass(frozen=True)
class BusRealtimeSnapshot:
    stop_id: int
    route_ids: tuple[int, ...]
    arrival_items: list[dict]


LEGACY_URL = "http://openapi.gbis.go.kr/ws/rest/busarrivalservice/station"
V2_URL = "https://apis.data.go.kr/6410000/busarrivalservice/v2/getBusArrivalListv2"
SAMPLE_API_KEY = "1234567890"


def required_text(parent: Tag, name: str) -> str:
    item = parent.find(name)
    if not isinstance(item, Tag):
        raise RuntimeError(f"Bus realtime API response is missing {name}")
    return item.text.strip()


async def get_realtime_data(stop_id: int, route_id_list: list[int]) -> BusRealtimeSnapshot:
    timeout = ClientTimeout(total=3.0)
    async with ClientSession(timeout=timeout) as session:
        api_key = os.getenv("BUS_API_KEY") or SAMPLE_API_KEY
        # Keep the legacy feed as a working fallback when a data.go.kr key is
        # absent or the additive GBIS v2 service is unavailable.
        if os.getenv("BUS_API_KEY"):
            try:
                async with session.get(
                    V2_URL,
                    params={"serviceKey": api_key, "stationId": stop_id, "format": "json"},
                ) as response:
                    response.raise_for_status()
                    return parse_realtime_v2_data(await response.json(), stop_id, route_id_list)
            except Exception as error:  # noqa: BLE001 - legacy snapshot remains available
                logging.warning("GBIS v2 failed for stop %s; trying the legacy feed: %s", stop_id, error)
        async with session.get(
            LEGACY_URL,
            params={"serviceKey": api_key, "stationId": stop_id},
        ) as response:
            response.raise_for_status()
            response_text = await response.text()
    return parse_realtime_data(response_text, stop_id, route_id_list)


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _v2_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    response = payload.get("response", payload)
    header = response.get("header", response.get("msgHeader", {}))
    result_code = str(header.get("resultCode", header.get("resultCode", "0")))
    if result_code not in {"0", "00"}:
        message = header.get("resultMessage", header.get("resultMsg", "unknown error"))
        raise RuntimeError(f"GBIS v2 request failed ({result_code}): {message}")
    body = response.get("body", response.get("msgBody", {}))
    items = body.get("items", body.get("item", body.get("busArrivalList", [])))
    if isinstance(items, dict):
        return [items]
    return items or []


def parse_realtime_v2_data(
    payload: dict[str, Any],
    stop_id: int,
    route_id_list: list[int],
    now: datetime | None = None,
) -> BusRealtimeSnapshot:
    route_id_set = set(route_id_list)
    updated_at = now or datetime.now(timezone(timedelta(hours=9)))
    arrival_items = []
    for item in _v2_items(payload):
        route_id = _optional_int(item.get("routeId"))
        if route_id is None or route_id not in route_id_set:
            continue
        for arrival_seq in (1, 2):
            location_no = _optional_int(item.get(f"locationNo{arrival_seq}"))
            if location_no is None or location_no < 0:
                continue
            predict_minutes = _optional_int(item.get(f"predictTime{arrival_seq}"))
            arrival_items.append({
                "route_id": route_id,
                "stop_id": stop_id,
                "arrival_seq": arrival_seq,
                "remaining_stop_count": location_no,
                "remaining_seat_count": _optional_int(item.get(f"remainSeatCnt{arrival_seq}")) or 0,
                "remaining_time": timedelta(minutes=predict_minutes or 0),
                "low_plate": _optional_int(item.get(f"lowPlate{arrival_seq}")) == 1,
                "current_stop_name": item.get(f"stationNm{arrival_seq}") or None,
                "plate_no": item.get(f"plateNo{arrival_seq}") or None,
                "crowded": _optional_int(item.get(f"crowded{arrival_seq}")),
                "state_code": _optional_int(item.get(f"stateCd{arrival_seq}")),
                "last_updated_time": updated_at,
            })
    return BusRealtimeSnapshot(stop_id, tuple(route_id_list), arrival_items)


def parse_realtime_data(response_text: str, stop_id: int, route_id_list: list[int]) -> BusRealtimeSnapshot:
    arrival_items: list[dict] = []
    soup = BeautifulSoup(response_text, features="xml")
    response_item = soup.find("response")
    if not isinstance(response_item, Tag):
        raise RuntimeError("Bus realtime API response is missing response")
    message_header = response_item.find("msgHeader")
    message_body = response_item.find("msgBody")
    if not isinstance(message_header, Tag) or not isinstance(message_body, Tag):
        raise RuntimeError("Bus realtime API response is missing header or body")
    result_code = required_text(message_header, "resultCode").strip()
    if result_code not in {"0", "00"}:
        result_message_item = message_header.find("resultMessage")
        result_message = result_message_item.text.strip() if isinstance(result_message_item, Tag) else "Unknown error"
        raise RuntimeError(f"Bus realtime API failed ({result_code}): {result_message}")
    arrival_list = message_body.find_all("busArrivalList")
    if not arrival_list:
        return BusRealtimeSnapshot(stop_id, tuple(route_id_list), [])

    query_time = required_text(message_header, "queryTime")
    updated_at = datetime.fromisoformat(query_time.replace("Z", "+00:00"))
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone(timedelta(hours=9)))
    route_id_set = set(route_id_list)
    for arrival_item in arrival_list:
        route_id = int(required_text(arrival_item, "routeId"))
        if route_id not in route_id_set:
            continue
        location_no_1 = required_text(arrival_item, "locationNo1")
        if location_no_1:
            arrival_items.append({
                "route_id": route_id,
                "stop_id": stop_id,
                "arrival_seq": 1,
                "remaining_stop_count": int(location_no_1),
                "remaining_seat_count": int(required_text(arrival_item, "remainSeatCnt1")),
                "remaining_time": timedelta(minutes=int(required_text(arrival_item, "predictTime1"))),
                "low_plate": int(required_text(arrival_item, "lowPlate1")) == 1,
                "current_stop_name": None,
                "plate_no": None,
                "crowded": None,
                "state_code": None,
                "last_updated_time": updated_at,
            })
        location_no_2 = required_text(arrival_item, "locationNo2")
        if location_no_2:
            arrival_items.append({
                "route_id": route_id,
                "stop_id": stop_id,
                "arrival_seq": 2,
                "remaining_stop_count": int(location_no_2),
                "remaining_seat_count": int(required_text(arrival_item, "remainSeatCnt2")),
                "remaining_time": timedelta(minutes=int(required_text(arrival_item, "predictTime2"))),
                "low_plate": int(required_text(arrival_item, "lowPlate2")) == 1,
                "current_stop_name": None,
                "plate_no": None,
                "crowded": None,
                "state_code": None,
                "last_updated_time": updated_at,
            })
    return BusRealtimeSnapshot(stop_id, tuple(route_id_list), arrival_items)
