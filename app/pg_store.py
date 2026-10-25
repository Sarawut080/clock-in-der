# ที่เก็บข้อมูลบน PostgreSQL (psycopg 3 + SQL ตรงๆ) — method ชุดเดียวกับ mock_store ตามสัญญาใน repositories.py
# กติกาเดียวกันใช้ทดสอบทั้งสอง backend: ถ้าสองตัวตอบไม่เหมือนกัน ชุดทดสอบจะล้ม
# ทุก query ใช้ placeholder %s เสมอ ห้ามต่อสตริงเอง (กัน SQL injection)
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterator, Optional

import psycopg
from psycopg import errors as pg_errors
from psycopg.rows import tuple_row
from psycopg_pool import ConnectionPool

from .errors import ApiError
from .mock_store import BKK
from .models import AttendanceEvent, Employee
from .repositories import AttendanceRepository, EmployeeRepository, ensure_can_clock

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "db" / "init.sql"


class Database:
    """ตัวถือ connection pool — open()/close() เรียกซ้ำได้ และเปิดใหม่หลังปิดได้ (lifespan ของแอปเริ่มซ้ำในชุดทดสอบ)"""

    def __init__(self, url: str, *, min_size: int = 1, max_size: int = 5):
        self._url = url
        self._min_size = min_size
        self._max_size = max_size
        self._pool: Optional[ConnectionPool] = None

    def _probe(self) -> None:
        """ลองต่อตรงหนึ่งครั้งก่อนเปิด pool — ต่อไม่ได้จะได้สาเหตุจริง (รหัสผิด/พอร์ตผิด/ไม่มีฐานข้อมูล) ทันที
        แทนที่จะรอ pool หมดเวลา 10 วินาทีแล้วได้แค่ "pool initialization incomplete" ที่ไม่บอกอะไร"""
        try:
            psycopg.connect(self._url, connect_timeout=5).close()
        except psycopg.Error as e:
            reason = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
            raise ConnectionError(
                f"ต่อฐานข้อมูลไม่ได้: {reason}\n"
                "ตรวจ DATABASE_URL ใน .env: พอร์ต (PostgreSQL 17 = 5433, 18 = 5432), ชื่อผู้ใช้/รหัสผ่าน "
                "(อักขระพิเศษต้องเข้ารหัส URL), ชื่อฐานข้อมูล และว่า service PostgreSQL กำลังรันอยู่"
            ) from None

    def open(self) -> None:
        if self._pool is not None:
            return
        self._probe()
        pool = ConnectionPool(
            self._url,
            min_size=self._min_size,
            max_size=self._max_size,
            # NFR6: ทุก connection ใช้เวลาไทย — ค่า timestamptz ที่อ่านกลับมาจึงเป็น +07:00
            kwargs={"options": "-c timezone=Asia/Bangkok", "row_factory": tuple_row},
            open=False,
        )
        try:
            pool.open(wait=True, timeout=10)  # ต่อไม่ได้ = ล้มทันทีตอนเริ่ม ไม่ใช่รอไปจนผู้ใช้กดแล้วค่อยพัง
        except Exception:
            pool.close()
            raise
        self._pool = pool

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool = None

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        """transaction เดียวต่อหนึ่ง with: จบปกติ = commit, เกิดข้อผิดพลาด = rollback"""
        if self._pool is None:
            raise RuntimeError("Database ยังไม่ได้ open()")
        with self._pool.connection() as conn:
            yield conn

    def ensure_schema(self) -> None:
        with self.connection() as conn:
            conn.execute(SCHEMA_FILE.read_text(encoding="utf-8"))

    def database_name(self) -> str:
        with self.connection() as conn:
            return conn.execute("SELECT current_database()").fetchone()[0]

    def wipe_all(self) -> None:
        """ล้างพนักงานและเวลาทั้งหมด แล้วเริ่มนับ id ใหม่จาก 1 — ใช้ผ่าน `python -m app.cli wipe-data` ที่บังคับพิมพ์ชื่อฐานข้อมูลยืนยัน
        (TRUNCATE ไม่ผ่าน trigger append-only โดยตั้งใจ: เป็นการล้างทั้งฐานข้อมูล ไม่ใช่การแก้บันทึกดิบทีละแถว)"""
        with self.connection() as conn:
            conn.execute("TRUNCATE attendance, employees RESTART IDENTITY CASCADE")

    def truncate_all(self) -> None:
        """ล้างข้อมูลทั้งหมด — ใช้ในชุดทดสอบเท่านั้น และปฏิเสธทันทีถ้าชื่อฐานข้อมูลไม่ลงท้าย _test"""
        with self.connection() as conn:
            name = conn.execute("SELECT current_database()").fetchone()[0]
            if not name.endswith("_test"):
                raise RuntimeError(f"ไม่ล้างข้อมูลของฐานข้อมูล {name!r} (ล้างได้เฉพาะชื่อที่ลงท้าย _test)")
            conn.execute("TRUNCATE attendance, employees RESTART IDENTITY CASCADE")


_EMPLOYEE_COLUMNS = "id, name, role, is_active, pin_hash"


def _employee(row) -> Employee:
    return Employee(id=row[0], name=row[1], role=row[2], is_active=row[3], pin_hash=row[4])


def _event(row) -> AttendanceEvent:
    return AttendanceEvent(id=row[0], employee_id=row[1], type=row[2], recorded_at=row[3].astimezone(BKK), photo_path=row[4])


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    # ค้นเป็นช่วง [00:00, วันถัดไป 00:00) ตามเวลาไทย — ใช้ index (employee_id, recorded_at) ได้ ต่างจากการแปลงทุกแถวเป็นวันที่
    start = datetime.combine(day, time.min, BKK)
    return start, start + timedelta(days=1)


class PgEmployeeRepository(EmployeeRepository):
    def __init__(self, db: Database):
        self._db = db

    def get_active(self, employee_id: int) -> Optional[Employee]:
        with self._db.connection() as conn:
            row = conn.execute(
                f"SELECT {_EMPLOYEE_COLUMNS} FROM employees WHERE id = %s AND is_active", (employee_id,)
            ).fetchone()
        return _employee(row) if row else None

    def list_active(self) -> list[Employee]:
        with self._db.connection() as conn:
            rows = conn.execute(f"SELECT {_EMPLOYEE_COLUMNS} FROM employees WHERE is_active ORDER BY name, id").fetchall()
        return [_employee(r) for r in rows]

    def list_all(self) -> list[Employee]:
        with self._db.connection() as conn:
            rows = conn.execute(f"SELECT {_EMPLOYEE_COLUMNS} FROM employees ORDER BY id").fetchall()
        return [_employee(r) for r in rows]

    def find_by_name(self, name: str) -> Optional[Employee]:
        with self._db.connection() as conn:
            row = conn.execute(
                f"SELECT {_EMPLOYEE_COLUMNS} FROM employees "
                "WHERE lower(regexp_replace(btrim(name), '\\s+', ' ', 'g')) = lower(regexp_replace(btrim(%s), '\\s+', ' ', 'g'))",
                (name,),
            ).fetchone()
        return _employee(row) if row else None

    def add(self, name: str, pin_hash: str, *, is_active: bool = True) -> Employee:
        try:
            with self._db.connection() as conn:
                row = conn.execute(
                    f"INSERT INTO employees (name, pin_hash, is_active) VALUES (%s, %s, %s) RETURNING {_EMPLOYEE_COLUMNS}",
                    (name, pin_hash, is_active),
                ).fetchone()
        except pg_errors.UniqueViolation:
            raise ApiError("NAME_TAKEN") from None  # unique index คือผู้ตัดสินสุดท้าย แม้หลาย process ลงชื่อเดียวกันพร้อมกัน
        return _employee(row)

    def set_pin_hash(self, employee_id: int, pin_hash: str) -> None:
        with self._db.connection() as conn:
            conn.execute("UPDATE employees SET pin_hash = %s WHERE id = %s", (pin_hash, employee_id))

    def count(self) -> int:
        with self._db.connection() as conn:
            return conn.execute("SELECT count(*) FROM employees").fetchone()[0]


class PgAttendanceRepository(AttendanceRepository):
    _COLUMNS = "id, employee_id, type, recorded_at, photo_path"

    def __init__(self, db: Database):
        self._db = db

    def add(self, employee_id: int, type_: str, photo_path: str, recorded_at: datetime) -> AttendanceEvent:
        with self._db.connection() as conn:
            row = conn.execute(
                f"INSERT INTO attendance (employee_id, type, recorded_at, photo_path) VALUES (%s, %s, %s, %s) RETURNING {self._COLUMNS}",
                (employee_id, type_, recorded_at, photo_path),
            ).fetchone()
        return _event(row)

    def record_checked(self, employee_id: int, type_: str, day: date, recorded_at: datetime, photo_path: str) -> AttendanceEvent:
        start, end = _day_bounds(day)
        with self._db.connection() as conn:
            # ล็อกแถวพนักงานคนนี้ไว้จน commit: กดเข้าซ้ำพร้อมกันจาก 2 connection/process จะต้องต่อคิว
            # คนที่สองเห็นเหตุการณ์ที่คนแรกเพิ่งบันทึกและถูก ensure_can_clock ปฏิเสธ (BR3)
            conn.execute("SELECT 1 FROM employees WHERE id = %s FOR UPDATE", (employee_id,))
            last = conn.execute(
                "SELECT type FROM attendance WHERE employee_id = %s AND recorded_at >= %s AND recorded_at < %s "
                "ORDER BY recorded_at DESC, id DESC LIMIT 1",
                (employee_id, start, end),
            ).fetchone()
            ensure_can_clock(type_, last[0] if last else None)
            row = conn.execute(
                f"INSERT INTO attendance (employee_id, type, recorded_at, photo_path) VALUES (%s, %s, %s, %s) RETURNING {self._COLUMNS}",
                (employee_id, type_, recorded_at, photo_path),
            ).fetchone()
        return _event(row)

    def events_of(self, employee_id: int, day: date) -> list[AttendanceEvent]:
        start, end = _day_bounds(day)
        with self._db.connection() as conn:
            rows = conn.execute(
                f"SELECT {self._COLUMNS} FROM attendance WHERE employee_id = %s AND recorded_at >= %s AND recorded_at < %s "
                "ORDER BY recorded_at, id",
                (employee_id, start, end),
            ).fetchall()
        return [_event(r) for r in rows]

    def count(self) -> int:
        with self._db.connection() as conn:
            return conn.execute("SELECT count(*) FROM attendance").fetchone()[0]
