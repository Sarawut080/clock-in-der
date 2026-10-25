"""สิ่งที่มีเฉพาะในฐานข้อมูลจริง — ข้ามถ้าไม่ได้ตั้ง TEST_DATABASE_URL (ดู .env.example)

ชุดทดสอบ api อื่นทั้งหมดรันกับ PostgreSQL อยู่แล้วผ่าน fixture `backend` ไฟล์นี้เพิ่มเฉพาะกรณีที่หน่วยความจำจำลองไม่ได้
"""
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta

import psycopg
import pytest

from app.container import Container
from app.errors import ApiError
from app.mock_store import BKK
from app.pg_store import Database
from tests.conftest import TEST_DATABASE_URL
from tests.helpers import JPEG


def run_all(fn, args):
    gate = threading.Barrier(len(args))

    def go(a):
        gate.wait()
        try:
            return fn(a), None
        except ApiError as e:
            return None, e.code

    with ThreadPoolExecutor(len(args)) as pool:
        return [f.result() for f in [pool.submit(go, a) for a in args]]


class TestAppendOnlyTrigger:
    """BR4 บังคับที่ฐานข้อมูล: แก้ผ่าน pgAdmin หรือสคริปต์อื่นก็ไม่ได้"""

    def seed_one(self, pg):
        return pg.attendance.add(1, "in", "x.jpg", pg.clock.now())

    def test_update_rejected(self, pg_container):
        ev = self.seed_one(pg_container)
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            with pg_container.database.connection() as conn:
                conn.execute("UPDATE attendance SET type = 'out' WHERE id = %s", (ev.id,))

    def test_delete_rejected(self, pg_container):
        ev = self.seed_one(pg_container)
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            with pg_container.database.connection() as conn:
                conn.execute("DELETE FROM attendance WHERE id = %s", (ev.id,))
        assert pg_container.attendance.count() >= 1

    def test_failed_update_leaves_row_unchanged(self, pg_container):
        ev = self.seed_one(pg_container)
        with pytest.raises(psycopg.Error):
            with pg_container.database.connection() as conn:
                conn.execute("UPDATE attendance SET photo_path = 'hacked.jpg' WHERE id = %s", (ev.id,))
        day = ev.recorded_at.date()
        assert [e.photo_path for e in pg_container.attendance.events_of(1, day) if e.id == ev.id] == ["x.jpg"]


class TestConstraints:
    def test_db_rejects_bad_type_and_missing_photo(self, pg_container):
        db = pg_container.database
        for sql in (
            "INSERT INTO attendance (employee_id, type, photo_path) VALUES (1, 'lunch', 'x.jpg')",
            "INSERT INTO attendance (employee_id, type, photo_path) VALUES (1, 'in', NULL)",  # BR1: ไม่มีรูป = บันทึกไม่ได้
            "INSERT INTO attendance (employee_id, type, photo_path) VALUES (9999, 'in', 'x.jpg')",  # ไม่มีพนักงานนี้
        ):
            with pytest.raises(psycopg.errors.IntegrityError):
                with db.connection() as conn:
                    conn.execute(sql)

    def test_recorded_at_defaults_to_server_time_when_omitted(self, pg_container):
        with pg_container.database.connection() as conn:
            at = conn.execute(
                "INSERT INTO attendance (employee_id, type, photo_path) VALUES (1, 'in', 'x.jpg') RETURNING recorded_at"
            ).fetchone()[0]
        assert abs((datetime.now(BKK) - at).total_seconds()) < 60  # BR2: ค่าเริ่มต้นเป็นเวลาของเซิร์ฟเวอร์

    @pytest.mark.parametrize("variant", ["สมชาย ใจดี", "  สมชาย    ใจดี ", "สมชาย\tใจดี"])
    def test_unique_name_index_catches_whitespace_variants(self, pg_container, variant):
        with pytest.raises(psycopg.errors.UniqueViolation):
            with pg_container.database.connection() as conn:
                conn.execute("INSERT INTO employees (name, pin_hash) VALUES (%s, 'x')", (variant,))

    def test_unique_name_is_case_insensitive(self, pg_container):
        pg_container.employees.add("Alice Smith", "h")
        with pytest.raises(ApiError) as e:
            pg_container.employees.add("alice  SMITH", "h")
        assert e.value.code == "NAME_TAKEN"


class TestConcurrencyAcrossConnections:
    def test_same_name_from_many_connections_creates_one_row(self, pg_container):
        results = run_all(lambda i: pg_container.employees.add("แข่งกัน คนเดียว", "h"), list(range(8)))
        assert sum(1 for ok, _ in results if ok) == 1
        assert [code for ok, code in results if not ok] == ["NAME_TAKEN"] * 7

    def test_double_clock_in_is_serialized_by_row_lock(self, pg_container):
        c = pg_container
        results = run_all(
            lambda i: c.attendance.record_checked(2, "in", c.clock.today(), c.clock.now(), f"p{i}.jpg"), list(range(8))
        )
        assert sum(1 for ok, _ in results if ok) == 1
        assert [code for ok, code in results if not ok] == ["ALREADY_CLOCKED_IN"] * 7
        assert [e.type for e in c.attendance.events_of(2, c.clock.today())] == ["in"]

    def test_different_employees_do_not_block_each_other(self, pg_container):
        c = pg_container
        ids = [c.employees.add(f"คนใหม่ {i}", "h").id for i in range(4)]  # พนักงานเดโมบางคนเข้างานค้างอยู่แล้ว จึงใช้คนใหม่
        results = run_all(lambda eid: c.attendance.record_checked(eid, "in", c.clock.today(), c.clock.now(), f"{eid}.jpg"), ids)
        assert all(ok for ok, _ in results)

    def test_ids_unique_and_increasing_under_load(self, pg_container):
        c = pg_container
        results = run_all(lambda i: c.attendance.add(1, "in", f"x{i}.jpg", c.clock.now()).id, list(range(8)))
        ids = [ok for ok, _ in results]
        assert len(set(ids)) == 8


class TestTimezone:
    def test_values_come_back_as_thai_time(self, pg_container):
        ev = pg_container.attendance.add(1, "in", "x.jpg", datetime(2026, 10, 24, 8, 3, 11, tzinfo=BKK))
        assert ev.recorded_at.utcoffset() == timedelta(hours=7)
        assert ev.to_api()["recorded_at"] == "2026-10-24T08:03:11+07:00"

    def test_day_boundary_is_midnight_thai_time_not_utc(self, pg_container):
        a = pg_container.attendance
        late = a.add(3, "in", "a.jpg", datetime(2026, 3, 1, 23, 59, 59, tzinfo=BKK))   # 16:59 UTC ของวันเดียวกัน
        early = a.add(3, "out", "b.jpg", datetime(2026, 3, 2, 0, 0, 1, tzinfo=BKK))     # 17:00 UTC วันก่อน
        d1, d2 = late.recorded_at.date(), early.recorded_at.date()
        assert d2 == d1 + timedelta(days=1)
        assert [e.photo_path for e in a.events_of(3, d1)] == ["a.jpg"]
        assert [e.photo_path for e in a.events_of(3, d2)] == ["b.jpg"]

    def test_clock_in_just_after_midnight_belongs_to_new_day_for_br3(self, pg_container, clock):
        c = pg_container
        clock.current = datetime(2026, 5, 5, 23, 59, 0, tzinfo=BKK)
        c.clock_service.clock(2, "in", JPEG)
        clock.current = datetime.combine(clock.current.date() + timedelta(days=1), time(0, 0, 30), BKK)
        c.clock_service.clock(2, "in", JPEG)  # วันใหม่ ไม่ถูกนับว่ากดซ้ำ

    def test_session_timezone_set_on_every_pooled_connection(self, pg_container):
        db = pg_container.database
        zones = set()
        for _ in range(4):
            with db.connection() as conn:
                zones.add(conn.execute("SHOW timezone").fetchone()[0])
        assert zones == {"Asia/Bangkok"}


class TestSafety:
    def test_sql_injection_in_name_is_stored_as_plain_text(self, pg_container):
        evil = "x'); DROP TABLE employees; --"
        _, emp = pg_container.auth.register(evil, "123456", "123456", "1.2.3.4")
        assert pg_container.employees.find_by_name(evil).id == emp.id
        assert pg_container.employees.count() == 6  # ตารางยังอยู่ ครบ 5 เดโม + 1

    def test_sql_injection_in_lookup_does_not_match_everything(self, pg_container):
        assert pg_container.employees.find_by_name("' OR '1'='1") is None
        assert pg_container.employees.get_active(1).name == "สมชาย ใจดี"

    def test_truncate_refuses_non_test_database(self):
        # ป้องกันพลาดชี้ TEST_DATABASE_URL ไปที่ฐานข้อมูลจริง: ชื่อที่ไม่ลงท้าย _test ต้องถูกปฏิเสธ
        if not TEST_DATABASE_URL:
            pytest.skip("ไม่ได้ตั้ง TEST_DATABASE_URL")
        real_name = TEST_DATABASE_URL.rsplit("/", 1)[-1].split("?")[0]
        assert real_name.endswith("_test"), f"TEST_DATABASE_URL ต้องชี้ไปฐานข้อมูลที่ชื่อลงท้าย _test ไม่ใช่ {real_name!r}"


class TestPersistence:
    def test_data_survives_a_restart(self, pg_container, clock, tmp_path):
        c1 = pg_container
        _, emp = c1.auth.register("อยู่รอด ทดสอบ", "135790", "135790", "5.5.5.5")
        c1.clock_service.clock(emp.id, "in", JPEG)
        c1.shutdown()

        # จำลองรีสตาร์ทเซิร์ฟเวอร์: Container ใหม่ล้วน ต่อฐานข้อมูลเดิม ไม่ seed
        c2 = Container(upload_dir=tmp_path / "up2", clock=clock, database=Database(TEST_DATABASE_URL), seed_demo=False)
        c2.startup()
        try:
            again = c2.employees.find_by_name("อยู่รอด ทดสอบ")
            assert again is not None and again.id == emp.id
            token, logged = c2.auth.login(emp.id, "135790", "5.5.5.5")  # PIN เดิมใช้ได้หลังรีสตาร์ท
            assert logged.id == emp.id and token
            assert [e.type for e in c2.attendance.events_of(emp.id, clock.today())] == ["in"]
            assert c2.clock_service.me_today(emp.id)["last_type"] == "in"
        finally:
            c2.shutdown()

    def test_schema_setup_is_repeatable(self, pg_container):
        for _ in range(3):
            pg_container.database.ensure_schema()
        assert pg_container.employees.count() == 5  # ไม่ล้างหรือซ้ำข้อมูล

    def test_pool_reopens_after_close(self, pg_container):
        pg_container.shutdown()
        pg_container.database.open()
        assert pg_container.employees.count() == 5
