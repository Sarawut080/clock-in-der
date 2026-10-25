from datetime import datetime, timedelta

from app.mock_store import BKK
from app.models import AttendanceEvent
from app.services import FULL_DAY_MINUTES, AttendanceSummarizer


def ev(i: int, type_: str, hh: int, mm: int = 0) -> AttendanceEvent:
    at = datetime(2026, 10, 24, hh, mm, tzinfo=BKK)
    return AttendanceEvent(id=i, employee_id=1, type=type_, recorded_at=at, photo_path="x.jpg")


def test_empty_day_is_short_with_no_times():
    s = AttendanceSummarizer.summarize([])
    assert (s.first_in, s.last_out, s.worked_minutes, s.is_complete, s.status) == (None, None, 0, True, "SHORT")


def test_exactly_eight_hours_is_ok():
    s = AttendanceSummarizer.summarize([ev(1, "in", 9), ev(2, "out", 17)])
    assert s.worked_minutes == FULL_DAY_MINUTES and s.status == "OK"


def test_one_minute_short_is_short():
    s = AttendanceSummarizer.summarize([ev(1, "in", 9), ev(2, "out", 16, 59)])
    assert s.worked_minutes == 479 and s.status == "SHORT"


def test_multiple_rounds_are_summed_d4():
    s = AttendanceSummarizer.summarize([ev(1, "in", 8), ev(2, "out", 12), ev(3, "in", 13), ev(4, "out", 17)])
    assert s.worked_minutes == 480 and s.status == "OK"
    assert (s.first_in, s.last_out) == ("08:00", "17:00")


def test_forgot_to_clock_out_is_incomplete_not_negative():
    s = AttendanceSummarizer.summarize([ev(1, "in", 8), ev(2, "out", 12), ev(3, "in", 13)])
    assert s.status == "INCOMPLETE" and not s.is_complete
    assert s.worked_minutes == 240  # รอบที่ปิดแล้วยังนับ
    assert s.last_out is None  # ยังไม่ออกงาน ห้ามแสดงเวลาออกของรอบก่อน


def test_seconds_are_floored_to_whole_minutes():
    a = AttendanceEvent(1, 1, "in", datetime(2026, 10, 24, 9, 0, 0, tzinfo=BKK), "x.jpg")
    b = AttendanceEvent(2, 1, "out", datetime(2026, 10, 24, 9, 0, 59, tzinfo=BKK), "y.jpg")
    assert AttendanceSummarizer.summarize([a, b]).worked_minutes == 0


def test_stray_out_without_in_is_ignored_and_never_negative():
    s = AttendanceSummarizer.summarize([ev(1, "out", 9), ev(2, "in", 10), ev(3, "out", 11)])
    assert s.worked_minutes == 60 and s.is_complete


def test_worked_minutes_never_negative_with_clock_skew():
    a = ev(1, "in", 10)
    b = AttendanceEvent(2, 1, "out", a.recorded_at - timedelta(minutes=5), "y.jpg")
    assert AttendanceSummarizer.summarize([a, b]).worked_minutes >= 0
