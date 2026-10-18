import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from main import _stale_ttl_seconds, execute_script
from scripts.realtime import BusRealtimeSnapshot, parse_realtime_data


EMPTY_RESPONSE = """
<response>
  <msgHeader>
    <queryTime>2026-07-18 02:00:00.000</queryTime>
    <resultCode>0</resultCode>
    <resultMessage>정상적으로 처리되었습니다.</resultMessage>
  </msgHeader>
  <msgBody />
</response>
"""

ERROR_RESPONSE = """
<response>
  <msgHeader>
    <resultCode>1</resultCode>
    <resultMessage>잘못된 정류소 ID입니다.</resultMessage>
  </msgHeader>
  <msgBody />
</response>
"""

NO_DATA_RESPONSE = """
<response>
  <msgHeader>
    <resultCode>4</resultCode>
    <resultMessage>운행중인 버스가 없습니다.</resultMessage>
  </msgHeader>
  <msgBody />
</response>
"""

ARRIVAL_RESPONSE = """
<response>
  <msgHeader>
    <queryTime>2026-07-18 19:27:36.281</queryTime>
    <resultCode>0</resultCode>
    <resultMessage>정상적으로 처리되었습니다.</resultMessage>
  </msgHeader>
  <msgBody>
    <busArrivalList>
      <locationNo1>9</locationNo1>
      <locationNo2 />
      <lowPlate1>0</lowPlate1>
      <lowPlate2>0</lowPlate2>
      <predictTime1>14</predictTime1>
      <predictTime2 />
      <remainSeatCnt1>41</remainSeatCnt1>
      <remainSeatCnt2>0</remainSeatCnt2>
      <routeId>216000061</routeId>
    </busArrivalList>
  </msgBody>
</response>
"""


def test_empty_api_response_is_a_successful_empty_snapshot():
    snapshot = parse_realtime_data(EMPTY_RESPONSE, 216000379, [216000061, 216000068])

    assert snapshot == BusRealtimeSnapshot(216000379, (216000061, 216000068), [])


def test_unsuccessful_api_response_is_not_an_empty_snapshot():
    with pytest.raises(RuntimeError, match="Bus realtime API failed"):
        parse_realtime_data(ERROR_RESPONSE, 216000379, [216000061])


def test_no_data_result_code_is_an_empty_snapshot():
    snapshot = parse_realtime_data(NO_DATA_RESPONSE, 216000379, [216000061])

    assert snapshot.stop_id == 216000379
    assert snapshot.route_ids == (216000061,)
    assert snapshot.arrival_items == []


def test_arrival_response_is_parsed_into_snapshot():
    snapshot = parse_realtime_data(ARRIVAL_RESPONSE, 216000379, [216000061])

    assert len(snapshot.arrival_items) == 1
    assert snapshot.arrival_items[0]["route_id"] == 216000061
    assert snapshot.arrival_items[0]["remaining_stop_count"] == 9
    assert snapshot.arrival_items[0]["remaining_seat_count"] == 41


def test_stale_ttl_defaults_to_120_when_unset(monkeypatch):
    monkeypatch.delenv("REALTIME_STALE_TTL_SECONDS", raising=False)

    assert _stale_ttl_seconds() == 120


def test_stale_ttl_uses_configured_value(monkeypatch):
    monkeypatch.setenv("REALTIME_STALE_TTL_SECONDS", "300")

    assert _stale_ttl_seconds() == 300


@pytest.mark.parametrize("raw_value", ["abc", "0"])
def test_stale_ttl_falls_back_to_120_for_invalid_value(monkeypatch, caplog, raw_value):
    monkeypatch.setenv("REALTIME_STALE_TTL_SECONDS", raw_value)

    with caplog.at_level(logging.WARNING):
        assert _stale_ttl_seconds() == 120

    assert any("REALTIME_STALE_TTL_SECONDS" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_successful_empty_stop_is_cleared_and_failed_stop_is_preserved():
    session = MagicMock(spec=Session)
    session.execute.side_effect = [
        [(216000379, 216000061), (216000138, 216000068)],
        MagicMock(),
        MagicMock(),
    ]
    empty_snapshot = BusRealtimeSnapshot(216000379, (216000061,), [])

    with patch(
        "main.get_realtime_data",
        new=AsyncMock(side_effect=[empty_snapshot, RuntimeError("timeout")]),
    ):
        await execute_script(session)

    assert session.execute.call_count == 3
    delete_statement = session.execute.call_args_list[1].args[0]
    params = delete_statement.compile().params
    assert params["stop_id_1"] == 216000379
    assert params["route_id_1"] == [216000061]
    cleanup_statement = session.execute.call_args_list[2].args[0]
    compiled_cleanup = str(cleanup_statement.compile(dialect=postgresql.dialect()))
    assert compiled_cleanup.startswith("DELETE FROM bus_realtime")
    assert "bus_realtime.last_updated_time < now() -" in compiled_cleanup
    session.commit.assert_called_once_with()


@pytest.mark.asyncio
async def test_all_failed_stops_preserve_existing_data():
    session = MagicMock(spec=Session)
    session.execute.return_value = [(216000379, 216000061)]

    with patch("main.get_realtime_data", new=AsyncMock(side_effect=RuntimeError("timeout"))):
        with pytest.raises(RuntimeError, match="All bus realtime fetches failed"):
            await execute_script(session)

    assert session.execute.call_count == 1
    session.commit.assert_not_called()
