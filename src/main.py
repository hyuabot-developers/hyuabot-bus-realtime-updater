import asyncio
from collections import defaultdict

import sqlalchemy
from sqlalchemy import select, delete
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
    except sqlalchemy.exc.OperationalError:
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

if __name__ == '__main__':
    asyncio.run(main())
