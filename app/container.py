# ประกอบ object ทั้งหมดไว้ที่เดียว (constructor injection) — เปลี่ยน repository เป็นของ DB จริงที่นี่จุดเดียว
from .mock_store import (
    UPLOAD_DIR,
    AttendanceRepository,
    DemoSeeder,
    EmployeeRepository,
    ServerClock,
    default_employees,
)
from .services import ClockService, PhotoStorage, ReportService


class Container:
    def __init__(self):
        self.upload_dir = UPLOAD_DIR
        self.clock = ServerClock()
        self.employees = EmployeeRepository(default_employees())
        self.attendance = AttendanceRepository(self.clock)
        self.photos = PhotoStorage(self.upload_dir)
        self.clock_service = ClockService(self.employees, self.attendance, self.clock, self.photos)
        self.report_service = ReportService(self.employees, self.attendance)
        self.seeder = DemoSeeder(self.employees, self.attendance, self.clock, self.upload_dir)
