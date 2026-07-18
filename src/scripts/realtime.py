from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from aiohttp import ClientTimeout, ClientSession
from bs4 import BeautifulSoup, Tag


@dataclass(frozen=True)
class BusRealtimeSnapshot:
    stop_id: int
    route_ids: tuple[int, ...]
    arrival_items: list[dict]


def required_text(parent: Tag, name: str) -> str:
    item = parent.find(name)
    if not isinstance(item, Tag):
        raise RuntimeError(f"Bus realtime API response is missing {name}")
    return item.text.strip()


async def get_realtime_data(stop_id: int, route_id_list: list[int]) -> BusRealtimeSnapshot:
    url = "http://openapi.gbis.go.kr/ws/rest/busarrivalservice/station" \
          f"?serviceKey=1234567890&stationId={stop_id}"
    timeout = ClientTimeout(total=3.0)
    async with ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            response.raise_for_status()
            response_text = await response.text()
    return parse_realtime_data(response_text, stop_id, route_id_list)


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
    updated_at = datetime.strptime(query_time, "%Y-%m-%d %H:%M:%S.%f").replace(
        tzinfo=timezone(timedelta(hours=9)),
    )
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
                "last_updated_time": updated_at,
            })
    return BusRealtimeSnapshot(stop_id, tuple(route_id_list), arrival_items)
