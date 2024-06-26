import asyncio
from datetime import datetime, timedelta, timezone

from aiohttp import ClientTimeout, ClientSession
from bs4 import BeautifulSoup, Tag
from sqlalchemy import insert
from sqlalchemy.orm import Session

from models import BusRealtime


async def get_realtime_data(db_session: Session, stop_id: str, route_id_list: list[str]) -> None:
    url = "http://openapi.gbis.go.kr/ws/rest/busarrivalservice/station" \
          f"?serviceKey=1234567890&stationId={stop_id}"
    arrival_items: list[dict] = []
    timeout = ClientTimeout(total=3.0)
    try:
        async with ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                soup = BeautifulSoup(await response.text(), features="xml")
                response_item = soup.find("response")
                if response_item is None:
                    return
                message_header = response_item.find("msgHeader")
                message_body = response_item.find("msgBody")
                if not isinstance(message_header, Tag) or not isinstance(message_body, Tag):
                    return
                query_time_item = message_header.find("queryTime")
                arrival_list = message_body.find_all("busArrivalList")
                if query_time_item is None or not arrival_list:
                    return
                query_time = query_time_item.text
                tz = timezone(timedelta(hours=9))
                for arrival_item in arrival_list:
                    if int(arrival_item.find("routeId").text) not in route_id_list:
                        continue
                    if arrival_item.find("locationNo1").text:
                        arrival_items.append({
                            "route_id": int(arrival_item.find("routeId").text),
                            "stop_id": stop_id,
                            "arrival_sequence": 1,
                            "remaining_stop_count": int(arrival_item.find("locationNo1").text),
                            "remaining_seat_count": int(arrival_item.find("remainSeatCnt1").text),
                            "remaining_time": timedelta(minutes=int(arrival_item.find("predictTime1").text)),
                            "low_plate": int(arrival_item.find("lowPlate1").text) == 1,
                            "last_updated_time": datetime.strptime(
                                query_time, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=tz),
                        })
                    if arrival_item.find("locationNo2").text:
                        arrival_items.append({
                            "route_id": int(arrival_item.find("routeId").text),
                            "stop_id": stop_id,
                            "arrival_sequence": 2,
                            "remaining_stop_count": int(arrival_item.find("locationNo2").text),
                            "remaining_seat_count": int(arrival_item.find("remainSeatCnt2").text),
                            "remaining_time": timedelta(minutes=int(arrival_item.find("predictTime2").text)),
                            "low_plate": int(arrival_item.find("lowPlate2").text) == 1,
                            "last_updated_time": datetime.strptime(
                                query_time, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=tz),
                        })
                if arrival_items:
                    insert_statement = insert(BusRealtime).values(arrival_items)
                    db_session.execute(insert_statement)
                db_session.commit()
    except asyncio.exceptions.TimeoutError:
        print("TimeoutError", url)
    except AttributeError:
        print("AttributeError", url)
