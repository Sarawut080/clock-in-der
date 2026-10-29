import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from app.errors import ApiError
from app.services import PhotoStorage
from tests.helpers import JPEG, tiny_png


def post_clock(client, type_="in", photo=("p.jpg", JPEG, "image/jpeg"), **form):
    files = {"photo": photo} if photo else None
    return client.post("/api/clock", data={"type": type_, **form}, files=files)


def code(r):
    return r.json().get("error")


def uploaded(container):
    return {p.name for p in container.upload_dir.iterdir() if not p.name.startswith("seed_")}


def test_full_day_state_machine(logged_in):
    client, emp_id = logged_in
    r = post_clock(client, "out")
    assert r.status_code == 409 and code(r) == "NOT_CLOCKED_IN"
    r = post_clock(client, "in")
    assert r.status_code == 200 and r.json()["type"] == "in" and r.json()["recorded_at"].endswith("+07:00")
    assert code(post_clock(client, "in")) == "ALREADY_CLOCKED_IN"
    assert post_clock(client, "out").status_code == 200
    assert code(post_clock(client, "out")) == "NOT_CLOCKED_IN"
    assert post_clock(client, "in").status_code == 200  # หลายรอบต่อวัน (D4)
    today = client.get("/api/me/today").json()
    assert today["employee_id"] == emp_id and today["last_type"] == "in"
    assert [e["type"] for e in today["events"]] == ["in", "out", "in"]
    assert today["is_complete"] is False


def test_worked_minutes_follow_server_clock(logged_in, clock):
    client, _ = logged_in
    post_clock(client, "in")
    clock.advance(hours=4, minutes=30)
    post_clock(client, "out")
    today = client.get("/api/me/today").json()
    assert today["worked_minutes"] == 270 and today["is_complete"] is True


class TestLiveHours:
    """ชั่วโมงสดของรอบที่ยังไม่ออกงาน — แสดงหน้าพนักงานเท่านั้น ไม่ทางการ: worked_minutes/is_complete ต้องไม่เปลี่ยนความหมาย"""

    @staticmethod
    def today(client):
        return client.get("/api/me/today").json()

    def test_no_events_means_zero_and_no_open_round(self, logged_in, clock):
        client, _ = logged_in
        t = self.today(client)
        assert (t["live_minutes"], t["worked_minutes"], t["open_since"]) == (0, 0, None)
        assert t["is_complete"] is True
        assert t["server_now"] == clock.current.isoformat(timespec="seconds")  # เวลาเซิร์ฟเวอร์ ไม่ใช่เวลาเครื่องผู้ใช้

    def test_running_round_counts_live_but_not_official(self, logged_in, clock):
        client, _ = logged_in
        started = clock.current
        post_clock(client, "in")
        clock.advance(hours=2, minutes=5)
        t = self.today(client)
        assert t["live_minutes"] == 125
        assert t["worked_minutes"] == 0 and t["is_complete"] is False  # ทางการยังเป็น INCOMPLETE (SA 7.3)
        assert t["open_since"] == started.isoformat(timespec="seconds")
        assert t["server_now"] == clock.current.isoformat(timespec="seconds")

    def test_live_minutes_grow_with_the_server_clock(self, logged_in, clock):
        client, _ = logged_in
        post_clock(client, "in")
        seen = []
        for _ in range(4):
            clock.advance(minutes=30)
            seen.append(self.today(client)["live_minutes"])
        assert seen == [30, 60, 90, 120]

    @pytest.mark.parametrize("seconds,expected", [(0, 0), (59, 0), (60, 1), (119, 1), (3600 + 59, 60)])
    def test_partial_minutes_are_floored(self, logged_in, clock, seconds, expected):
        client, _ = logged_in
        post_clock(client, "in")
        clock.advance(seconds=seconds)
        assert self.today(client)["live_minutes"] == expected

    def test_closed_rounds_plus_running_round(self, logged_in, clock):
        client, _ = logged_in
        post_clock(client, "in")
        clock.advance(hours=1)
        post_clock(client, "out")      # ปิดรอบแรก = 60 นาทีทางการ
        clock.advance(minutes=30)      # พัก ไม่นับ
        post_clock(client, "in")
        clock.advance(minutes=30)      # รอบที่สองกำลังนับ
        t = self.today(client)
        assert t["worked_minutes"] == 60 and t["live_minutes"] == 90 and t["is_complete"] is False

    def test_clock_out_freezes_live_to_the_official_number(self, logged_in, clock):
        client, _ = logged_in
        post_clock(client, "in")
        clock.advance(hours=3)
        post_clock(client, "out")
        clock.advance(hours=5)  # เวลาผ่านไปต่อ ตัวเลขต้องไม่ขยับอีก
        t = self.today(client)
        assert t["live_minutes"] == t["worked_minutes"] == 180
        assert t["open_since"] is None and t["is_complete"] is True

    def test_round_left_open_overnight_does_not_carry_into_the_next_day(self, logged_in, clock):
        client, _ = logged_in
        post_clock(client, "in")
        clock.advance(days=1)
        t = self.today(client)
        assert (t["live_minutes"], t["open_since"], t["last_type"]) == (0, None, None)  # BR3 นับเฉพาะวันนี้

    def test_live_fields_never_leak_into_the_report_contract(self, logged_in, clock):
        client, _ = logged_in
        post_clock(client, "in")
        clock.advance(hours=1)
        rows = client.get(f"/api/report/daily?date={clock.current.date().isoformat()}").json()
        mine = next(r for r in rows if r["name"] == "ผู้ทดสอบ ระบบ")
        assert mine["status"] == "INCOMPLETE" and mine["worked_minutes"] == 0  # แดชบอร์ดไม่นับรอบที่ยังไม่ออก
        assert not {"live_minutes", "open_since", "server_now"} & set(mine)


class TestRequests:
    def test_photo_required(self, logged_in):
        client, _ = logged_in
        assert code(post_clock(client, "in", photo=None)) == "PHOTO_REQUIRED"
        assert code(post_clock(client, "in", photo=("p.jpg", b"", "image/jpeg"))) == "PHOTO_REQUIRED"
        assert client.get("/api/me/today").json()["events"] == []  # ล้มแล้วต้องไม่มีเหตุการณ์หลุดเข้ามา

    @pytest.mark.parametrize("bad", ["x", "IN", "", "in ", "out;"])
    def test_bad_type(self, logged_in, bad):
        client, _ = logged_in
        r = post_clock(client, bad)
        assert r.status_code == 400 and code(r) == "BAD_REQUEST"

    def test_missing_type(self, logged_in):
        client, _ = logged_in
        r = client.post("/api/clock", files={"photo": ("p.jpg", JPEG, "image/jpeg")})
        assert r.status_code == 400 and code(r) == "BAD_REQUEST"

    def test_server_time_only_client_time_ignored_br2(self, logged_in, clock):
        client, _ = logged_in
        r = post_clock(client, "in", recorded_at="2001-01-01T00:00:00+07:00", time="00:00")
        assert r.status_code == 200
        assert r.json()["recorded_at"] == clock.current.isoformat(timespec="seconds")

    def test_non_numeric_employee_id_uses_contract_error_format(self, logged_in):
        client, _ = logged_in
        r = post_clock(client, "in", employee_id="abc")
        assert r.status_code == 400 and code(r) == "BAD_REQUEST" and r.json()["ok"] is False

    def test_cannot_clock_for_someone_else_br5(self, logged_in):
        client, my_id = logged_in
        r = post_clock(client, "in", employee_id="1")
        assert r.status_code == 403 and code(r) == "FORBIDDEN"
        assert client.get("/api/me/today?employee_id=1").status_code == 403
        assert post_clock(client, "in", employee_id=str(my_id)).status_code == 200  # ส่ง id ของตัวเองได้


class TestPhotos:
    def test_extension_comes_from_content_not_filename(self, logged_in, container):
        client, emp_id = logged_in
        r = post_clock(client, "in", photo=("holiday.jpg", tiny_png(), "image/jpeg"))
        assert r.status_code == 200
        names = [n for n in uploaded(container) if n.startswith(f"{emp_id}_")]
        assert len(names) == 1 and names[0].endswith(".png")

    @pytest.mark.parametrize(
        "name,content,mime",
        [
            ("a.jpg", b"hello world", "image/jpeg"),
            ("a.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "image/svg+xml"),
            ("a.jpg", b"<html><script>alert(1)</script></html>", "image/jpeg"),
            ("a.jpg", b"GIF89a", "image/gif"),
            ("a.jpg", b"\xff\xd8", "image/jpeg"),
        ],
    )
    def test_non_images_rejected_and_not_stored(self, logged_in, container, name, content, mime):
        client, _ = logged_in
        before = uploaded(container)
        r = post_clock(client, "in", photo=(name, content, mime))
        assert r.status_code == 400 and code(r) == "INVALID_PHOTO"
        assert uploaded(container) == before
        assert client.get("/api/me/today").json()["events"] == []

    def test_oversize_rejected(self, logged_in, container):
        client, _ = logged_in
        before = uploaded(container)
        big = JPEG + b"\x00" * (PhotoStorage.MAX_BYTES + 1)
        r = post_clock(client, "in", photo=("big.jpg", big, "image/jpeg"))
        assert r.status_code == 413 and code(r) == "PHOTO_TOO_LARGE"
        assert uploaded(container) == before

    def test_huge_upload_rejected_from_content_length_before_body(self, logged_in):
        client, _ = logged_in
        big = JPEG + b"\x00" * (PhotoStorage.MAX_BYTES + 200 * 1024)
        r = post_clock(client, "in", photo=("big.jpg", big, "image/jpeg"))
        assert r.status_code == 413 and code(r) == "PHOTO_TOO_LARGE"

    def test_rejected_photo_does_not_consume_the_clock_state(self, logged_in):
        client, _ = logged_in
        assert code(post_clock(client, "in", photo=("a.jpg", b"nope", "image/jpeg"))) == "INVALID_PHOTO"
        assert post_clock(client, "in").status_code == 200  # ยังกดเข้างานได้ตามปกติ

    def test_rule_violation_leaves_no_orphan_photo(self, logged_in, container):
        client, emp_id = logged_in
        assert post_clock(client, "in").status_code == 200
        assert len([n for n in uploaded(container) if n.startswith(f"{emp_id}_")]) == 1
        assert code(post_clock(client, "in")) == "ALREADY_CLOCKED_IN"  # BR3 ปฏิเสธหลังรับรูปมาแล้ว
        assert len([n for n in uploaded(container) if n.startswith(f"{emp_id}_")]) == 1  # รูปของรอบที่ปฏิเสธถูกลบ


class TestDayBoundary:
    """BR3 นับเฉพาะวันนี้: ลืมกดออกเมื่อวาน วันนี้ก็ยังเข้างานได้"""

    def test_forgot_clock_out_yesterday_can_clock_in_today(self, logged_in, clock):
        client, _ = logged_in
        assert post_clock(client, "in").status_code == 200
        clock.advance(days=1)
        assert client.get("/api/me/today").json()["events"] == []
        assert post_clock(client, "in").status_code == 200

    def test_midnight_rollover_keeps_history_as_incomplete(self, logged_in, clock):
        client, _ = logged_in
        post_clock(client, "in")
        day_one = clock.current.date()
        clock.advance(hours=15)  # 09:00 → 00:00 วันถัดไป
        assert code(post_clock(client, "out")) == "NOT_CLOCKED_IN"
        rows = client.get(f"/api/report/daily?date={day_one.isoformat()}").json()
        mine = [r for r in rows if r["name"] == "ผู้ทดสอบ ระบบ"]
        assert len(mine) == 1 and mine[0]["status"] == "INCOMPLETE" and mine[0]["last_out"] is None

    def test_exact_eight_hours_is_ok_in_report(self, logged_in, clock):
        client, _ = logged_in
        post_clock(client, "in")
        clock.advance(hours=8)
        post_clock(client, "out")
        rows = client.get(f"/api/report/daily?date={clock.current.date().isoformat()}").json()
        mine = next(r for r in rows if r["name"] == "ผู้ทดสอบ ระบบ")
        assert mine["worked_minutes"] == 480 and mine["status"] == "OK"


class TestConcurrency:
    def test_double_tap_in_exactly_one_succeeds(self, container):
        emp = container.employees.get_active(2)
        outcomes = []
        gate = threading.Barrier(8)

        def tap():
            gate.wait()
            try:
                container.clock_service.clock(emp.id, "in", JPEG)
                outcomes.append("ok")
            except ApiError as e:
                outcomes.append(e.code)

        with ThreadPoolExecutor(8) as pool:
            for f in [pool.submit(tap) for _ in range(8)]:
                f.result()  # ข้อผิดพลาดที่ไม่คาดคิดในเธรดต้องทำให้ทดสอบล้ม ไม่ถูกกลืนหาย
        assert outcomes.count("ok") == 1 and outcomes.count("ALREADY_CLOCKED_IN") == 7

    def test_concurrent_registration_same_name_creates_one_account(self, container):
        outcomes = []
        gate = threading.Barrier(8)

        def reg(i):
            gate.wait()
            try:
                container.auth.register("แข่งกัน ลงทะเบียน", "123456", "123456", f"10.0.0.{i}")
                outcomes.append("ok")
            except ApiError as e:
                outcomes.append(e.code)

        with ThreadPoolExecutor(8) as pool:
            for f in [pool.submit(reg, i) for i in range(8)]:
                f.result()
        assert outcomes.count("ok") == 1 and outcomes.count("NAME_TAKEN") == 7
        assert len([e for e in container.employees.list_all() if e.name == "แข่งกัน ลงทะเบียน"]) == 1

    def test_concurrent_registration_distinct_names_get_unique_ids(self, container):
        gate = threading.Barrier(8)

        def reg(i):
            gate.wait()
            return container.auth.register(f"คนที่ {i}", "123456", "123456", f"10.0.1.{i}")[1].id

        with ThreadPoolExecutor(8) as pool:
            ids = list(pool.map(reg, range(8)))
        assert len(set(ids)) == 8

    def test_attendance_ids_unique_under_load(self, container):
        gate = threading.Barrier(8)

        def add(i):
            gate.wait()
            return container.attendance.add(1, "in", f"x{i}.jpg", container.clock.now()).id

        with ThreadPoolExecutor(8) as pool:
            ids = list(pool.map(add, range(8)))
        assert len(set(ids)) == 8
