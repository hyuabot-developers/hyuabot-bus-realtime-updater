import asyncio
import os
import time
from collections import defaultdict

from sqlalchemy import select, delete
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from models import BusRouteStop, BusRealtime
from scripts.realtime import get_realtime_data
from utils.database import get_db_engine, get_master_db_engine


async def main():
    connection = get_db_engine()
    session_constructor = sessionmaker(bind=connection)
    session = session_constructor()
    if session is None:
        raise RuntimeError("Failed to get db session")
    try:
        await execute_script(session)
    except OperationalError:
        connection = get_master_db_engine()
        session_constructor = sessionmaker(bind=connection)
        session = session_constructor()
        await execute_script(session)


async def execute_script(session):
    stop_group = defaultdict(list)
    stop_query = select(BusRouteStop.stop_id, BusRouteStop.route_id)
    session.execute(stop_query)
    session.execute(delete(BusRealtime))
    for stop_id, route_id in session.execute(stop_query):
        stop_group[stop_id].append(route_id)
    job_list = []
    for stop_id, route_id_list in stop_group.items():
        job_list.append(get_realtime_data(session, stop_id, route_id_list))
    await asyncio.gather(*job_list)
    session.close()


async def run_loop():
    # CronJob fires every minute; loop several times within that window to
    # achieve sub-minute refresh. Tuned via LOOP_ITERATIONS / LOOP_INTERVAL_SECONDS
    # (default: every 15s, 4 iterations per minute). Pacing keeps the loop inside
    # the 60s window so consecutive CronJob runs never overlap.
    iterations = int(os.getenv("LOOP_ITERATIONS", "4"))
    interval = float(os.getenv("LOOP_INTERVAL_SECONDS", "15"))
    for i in range(iterations):
        started_at = time.monotonic()
        try:
            await main()
        except Exception as e:  # noqa: BLE001 - keep loop alive on transient errors
            print("Bus realtime iteration failed:", e)
        if i < iterations - 1:
            await asyncio.sleep(max(0.0, interval - (time.monotonic() - started_at)))


if __name__ == '__main__':
    asyncio.run(run_loop())
