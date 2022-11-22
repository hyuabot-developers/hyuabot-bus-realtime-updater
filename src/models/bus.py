from sqlalchemy import PrimaryKeyConstraint, Column
from sqlalchemy.sql import sqltypes

from models import BaseModel


class BusRouteStop(BaseModel):
    __tablename__ = "bus_route_stop"
    __table_args__ = (PrimaryKeyConstraint("route_id", "stop_id"),)
    route_id = Column(sqltypes.Integer, nullable=False)
    stop_id = Column(sqltypes.Integer, nullable=False)
    stop_sequence = Column(sqltypes.Integer, nullable=False)


class BusRealtime(BaseModel):
    __tablename__ = "bus_realtime"
    __table_args__ = (PrimaryKeyConstraint("route_id", "stop_id", "arrival_sequence"),)
    stop_id = Column(sqltypes.Integer, nullable=False)
    route_id = Column(sqltypes.Integer, nullable=False)
    arrival_sequence = Column(sqltypes.Integer, nullable=False)
    remaining_stop_count = Column(sqltypes.Integer, nullable=False)
    remaining_seat_count = Column(sqltypes.Integer, nullable=False)
    remaining_time = Column(sqltypes.Integer, nullable=False)
    low_plate = Column(sqltypes.Boolean, nullable=False)
