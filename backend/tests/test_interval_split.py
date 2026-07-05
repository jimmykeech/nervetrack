from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.services.interval_split import DaySegment, day_segments, local_midnight_utc

UTC = ZoneInfo("UTC")
SYD = ZoneInfo("Australia/Sydney")


def test_local_midnight_utc_in_utc():
    assert local_midnight_utc(date(2026, 6, 13), UTC) == datetime(2026, 6, 13, 0, 0)


def test_local_midnight_utc_respects_dst_offsets():
    # Sydney midnight is UTC+10 (standard) on 4 Oct 2026 (before the 02:00 spring-forward)
    assert local_midnight_utc(date(2026, 10, 4), SYD) == datetime(2026, 10, 3, 14, 0)
    # and UTC+11 (daylight) on 5 Apr 2026 (before the 03:00 fall-back)
    assert local_midnight_utc(date(2026, 4, 5), SYD) == datetime(2026, 4, 4, 13, 0)


def test_single_day_span_is_identity():
    segs = day_segments(datetime(2026, 6, 13, 9, 0), datetime(2026, 6, 13, 10, 0), UTC)
    assert segs == [DaySegment(date(2026, 6, 13), datetime(2026, 6, 13, 9, 0),
                               datetime(2026, 6, 13, 10, 0), 3600)]


def test_overnight_span_splits_into_two_days():
    segs = day_segments(datetime(2026, 6, 13, 22, 0), datetime(2026, 6, 14, 7, 0), UTC)
    assert [s.entry_date for s in segs] == [date(2026, 6, 13), date(2026, 6, 14)]
    assert [s.duration_seconds for s in segs] == [7200, 25200]
    assert segs[0].ended_at == datetime(2026, 6, 14, 0, 0)
    assert segs[1].started_at == datetime(2026, 6, 14, 0, 0)


def test_multi_day_span_has_a_full_middle_day():
    segs = day_segments(datetime(2026, 6, 13, 22, 0), datetime(2026, 6, 15, 3, 0), UTC)
    assert [s.entry_date for s in segs] == [date(2026, 6, 13), date(2026, 6, 14), date(2026, 6, 15)]
    assert [s.duration_seconds for s in segs] == [7200, 86400, 10800]


def test_exact_midnight_end_yields_one_segment():
    segs = day_segments(datetime(2026, 6, 13, 22, 0), datetime(2026, 6, 14, 0, 0), UTC)
    assert len(segs) == 1
    assert segs[0].entry_date == date(2026, 6, 13)


def test_empty_when_end_not_after_start():
    assert day_segments(datetime(2026, 6, 13, 10, 0), datetime(2026, 6, 13, 10, 0), UTC) == []


def test_split_at_local_midnight_under_dst():
    # 23:30–00:30 Sydney local across 3→4 Oct 2026; local midnight is 14:00 UTC that day.
    segs = day_segments(datetime(2026, 10, 3, 13, 30), datetime(2026, 10, 3, 14, 30), SYD)
    assert [s.entry_date for s in segs] == [date(2026, 10, 3), date(2026, 10, 4)]
    assert [s.duration_seconds for s in segs] == [1800, 1800]
