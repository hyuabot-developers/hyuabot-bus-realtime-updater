import asyncio
from collections import defaultdict

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from models import BaseModel, BusRealtime, BusRouteStop
from scripts.realtime import get_realtime_data
from utils.database import get_db_engine
from tests.insert_bus_information import initialize_bus_data


class TestFetchRealtimeData:
    connection: Engine | None = None
    session_constructor = None
    session: Session | None = None

    @classmethod
    def setup_class(cls):
        cls.connection = get_db_engine()
        cls.session_constructor = sessionmaker(bind=cls.connection)
        # Database session check
        cls.session = cls.session_constructor()
        assert cls.session is not None
        # Migration schema check
        BaseModel.metadata.create_all(cls.connection)
        # Insert initial data
        asyncio.run(initialize_bus_data(cls.session))
        cls.session.commit()
        cls.session.close()

    @pytest.mark.asyncio
    async def test_fetch_realtime_data(self):
        connection = get_db_engine()
        session_constructor = sessionmaker(bind=connection)
        # Database session check
        session = session_constructor()
        # Get list to fetch
        stop_group = defaultdict(list)
        stop_query = select(BusRouteStop.stop_id, BusRouteStop.route_id)
        session.execute(stop_query)
        for stop_id, route_id in session.execute(stop_query):
            stop_group[stop_id].append(route_id)
        job_list = []
        for stop_id, route_id_list in stop_group.items():
            job_list.append(get_realtime_data(session, stop_id, route_id_list))
        await asyncio.gather(*job_list)

        # Check if the data is inserted
        arrival_list = session.query(BusRealtime).all()
        for arrival_item in arrival_list:  # type: BusRealtime
            assert type(arrival_item.route_id) == int
            assert type(arrival_item.stop_id) == int
            assert type(arrival_item.arrival_sequence) == int
            assert type(arrival_item.remaining_stop_count) == int
            assert type(arrival_item.remaining_seat_count) == int
            assert type(arrival_item.remaining_time) == int
            assert type(arrival_item.low_plate) == bool
