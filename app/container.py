# ประกอบ object ทั้งหมดไว้ที่เดียว (constructor injection) — เลือกที่เก็บข้อมูล (หน่วยความจำ / PostgreSQL) ที่นี่จุดเดียว
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from .auth import AuthGuard, AuthService, LoginThrottle, PinHasher, SessionStore
from .mock_store import (
    UPLOAD_DIR,
    DemoSeeder,
    InMemoryAttendanceRepository,
    InMemoryEmployeeRepository,
    ServerClock,
)
from .pg_store import Database, PgAttendanceRepository, PgEmployeeRepository
from .services import ClockService, PhotoStorage, ReportService

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Container:
    def __init__(
        self,
        upload_dir: Optional[Path] = None,
        clock: Optional[ServerClock] = None,
        database: Optional[Database] = None,
        seed_demo: bool = True,
    ):
        """database=None → ข้อมูลในหน่วยความจำ · seed_demo → ใส่พนักงาน/ประวัติเดโม (ที่เก็บต้องว่างเปล่า)
        รับ upload_dir / clock จากภายนอกได้ ให้ชุดทดสอบใช้โฟลเดอร์ชั่วคราวและนาฬิกาปลอม"""
        self.upload_dir = upload_dir or UPLOAD_DIR
        self.clock = clock or ServerClock()
        self.database = database
        if database is None:
            self.employees = InMemoryEmployeeRepository()
            self.attendance = InMemoryAttendanceRepository()
        else:
            self.employees = PgEmployeeRepository(database)
            self.attendance = PgAttendanceRepository(database)
        self.photos = PhotoStorage(self.upload_dir)
        self.clock_service = ClockService(self.employees, self.attendance, self.clock, self.photos)
        self.report_service = ReportService(self.employees, self.attendance)
        self.hasher = PinHasher()
        self.auth = AuthService(self.employees, self.hasher, LoginThrottle(), SessionStore())
        self.guard = AuthGuard(self.auth)
        self.seeder = (
            DemoSeeder(self.employees, self.attendance, self.clock, self.upload_dir, self.hasher.hash) if seed_demo else None
        )

    @classmethod
    def from_env(cls) -> "Container":
        """ตั้ง DATABASE_URL (ใน .env หรือ environment) = ใช้ PostgreSQL จริง ไม่ใส่ข้อมูลเดโม · ไม่ตั้ง = เดโมในหน่วยความจำ"""
        load_dotenv(ENV_FILE)
        url = os.environ.get("DATABASE_URL", "").strip()
        database = Database(url) if url else None
        return cls(database=database, seed_demo=database is None)

    def startup(self) -> None:
        """เรียกซ้ำได้ — เปิดฐานข้อมูล สร้างตารางที่ยังไม่มี แล้ว seed เดโม (ถ้าเปิดใช้)"""
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        if self.database is not None:
            self.database.open()
            self.database.ensure_schema()
        if self.seeder is not None:
            self.seeder.seed()

    def shutdown(self) -> None:
        if self.database is not None:
            self.database.close()
