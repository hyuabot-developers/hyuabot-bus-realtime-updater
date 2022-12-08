import datetime

from sqlalchemy import String, Time, PrimaryKeyConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase


class BaseModel(DeclarativeBase):
    pass


class BusRoute(BaseModel):
    __tablename__ = "bus_route"
    route_id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(nullable=False)
    company_name: Mapped[str] = mapped_column(String(30), nullable=False)
    company_telephone: Mapped[str] = mapped_column(String(15), nullable=False)
    district_code: Mapped[int] = mapped_column(nullable=False)
    up_first_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    up_last_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    down_first_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    down_last_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    start_stop_id: Mapped[int] = mapped_column(nullable=False)
    end_stop_id: Mapped[int] = mapped_column(nullable=False)
    route_name: Mapped[str] = mapped_column(String(30), nullable=False)
    route_type_code: Mapped[str] = mapped_column(String(10), nullable=False)
    route_type_name: Mapped[str] = mapped_column(String(10), nullable=False)


class BusStop(BaseModel):
    __tablename__ = "bus_stop"
    stop_id: Mapped[int] = mapped_column(primary_key=True)
    stop_name: Mapped[str] = mapped_column(String(30), nullable=False)
    district_code: Mapped[int] = mapped_column(nullable=False)
    mobile_number: Mapped[str] = mapped_column(String(15), nullable=False)
    region_name: Mapped[str] = mapped_column(String(10), nullable=False)
    latitude: Mapped[float] = mapped_column(nullable=False)
    longitude: Mapped[float] = mapped_column(nullable=False)


class BusRouteStop(BaseModel):
    __tablename__ = "bus_route_stop"
    __table_args__ = (PrimaryKeyConstraint("route_id", "stop_id", name="pk_bus_route_stop"),)
    route_id: Mapped[int] = mapped_column(ForeignKey("bus_route.route_id"), nullable=False)
    stop_id: Mapped[int] = mapped_column(ForeignKey("bus_stop.stop_id"), nullable=False)
    stop_sequence: Mapped[int] = mapped_column(nullable=False)


class BusRealtime(BaseModel):
    __tablename__ = "bus_realtime"
    __table_args__ = (PrimaryKeyConstraint(
        "route_id", "stop_id", "arrival_sequence", name="pk_bus_realtime"),)
    stop_id: Mapped[int] = mapped_column(ForeignKey("bus_stop.stop_id"), nullable=False)
    route_id: Mapped[int] = mapped_column(ForeignKey("bus_route.route_id"), nullable=False)
    arrival_sequence: Mapped[int] = mapped_column(nullable=False)
    remaining_stop_count: Mapped[int] = mapped_column(nullable=False)
    remaining_seat_count: Mapped[int] = mapped_column(nullable=False)
    remaining_time: Mapped[int] = mapped_column(nullable=False)
    low_plate: Mapped[bool] = mapped_column(nullable=False)
    last_updated_time: Mapped[datetime.datetime] = mapped_column(nullable=False)
