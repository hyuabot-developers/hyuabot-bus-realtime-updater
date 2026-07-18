import asyncio
import os
import time
from collections import defaultdict

from sqlalchemy import and_, select, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from models import BusRouteStop, BusRealtime
from scripts.realtime import BusRealtimeSnapshot, get_realtime_data
from utils.database import get_db_engine, get_master_db_engine


async def main():
    connection = get_db_engine()
    try:
        await execute_with_connection(connection)
    except OperationalError:
        connection = get_master_db_engine()
        await execute_with_connection(connection)


async def execute_with_connection(connection):
    session_constructor = sessionmaker(bind=connection)
    session = session_constructor()
    try:
        await execute_script(session)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def execute_script(session):
    stop_group = defaultdict(list)
    stop_query = select(BusRouteStop.stop_id, BusRouteStop.route_id)
    for stop_id, route_id in session.execute(stop_query):
        stop_group[stop_id].append(route_id)
    job_list = [get_realtime_data(stop_id, route_id_list) for stop_id, route_id_list in stop_group.items()]
    results = await asyncio.gather(*job_list, return_exceptions=True)
    snapshots: list[BusRealtimeSnapshot] = []
    for stop_id, result in zip(stop_group.keys(), results):
        if isinstance(result, BaseException):
            print(f"Bus realtime fetch failed for stop {stop_id}:", result)
        else:
            snapshots.append(result)
    if stop_group and not snapshots:
        raise RuntimeError("All bus realtime fetches failed")
    for snapshot in snapshots:
        session.execute(delete(BusRealtime).where(and_(
            BusRealtime.stop_id == snapshot.stop_id,
            BusRealtime.route_id.in_(snapshot.route_ids),
        )))
        if snapshot.arrival_items:
            insert_statement = insert(BusRealtime).values(snapshot.arrival_items)
            session.execute(insert_statement)
    session.commit()


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
