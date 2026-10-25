# ข้อมูลสมมติในหน่วยความจำ แทน PostgreSQL ชั่วคราว (mockup)
# ตอนต่อ DB จริง: เปลี่ยนเฉพาะไฟล์นี้ให้ query ตาราง employees / attendance — services, router กับหน้าเว็บไม่ต้องแก้
# (เขียน repository ตัวใหม่ที่มี method ชุดเดียวกับ EmployeeRepository / AttendanceRepository)
# ข้อมูลหายทุกครั้งที่รีสตาร์ทเซิร์ฟเวอร์ (ตั้งใจ — เป็นแค่ข้อมูลเดโม)
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional

from .models import AttendanceEvent, Employee

BKK = timezone(timedelta(hours=7))  # NFR6: เวลาไทย (ไทยไม่มี daylight saving จึงใช้ +7 ตายตัวได้)
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"


class ServerClock:
    """BR2: เวลามาจากนาฬิกาเซิร์ฟเวอร์เสมอ"""

    def now(self) -> datetime:
        return datetime.now(BKK).replace(microsecond=0)

    def today(self) -> date:
        return self.now().date()


class EmployeeRepository:
    def __init__(self, employees: list[Employee]):
        self._employees = employees

    def get_active(self, employee_id: int) -> Optional[Employee]:
        for emp in self._employees:
            if emp.id == employee_id and emp.is_active:
                return emp
        return None

    def list_active(self) -> list[Employee]:
        # เรียงตามชื่อ ให้เมนูเลือกชื่อหาง่าย
        return sorted((e for e in self._employees if e.is_active), key=lambda e: e.name)

    def list_all(self) -> list[Employee]:
        return list(self._employees)


class AttendanceRepository:
    def __init__(self, clock: ServerClock):
        self._clock = clock
        self._events: list[AttendanceEvent] = []

    def add(self, employee_id: int, type_: str, photo_path: str, recorded_at: Optional[datetime] = None) -> AttendanceEvent:
        event = AttendanceEvent(
            id=len(self._events) + 1,
            employee_id=employee_id,
            type=type_,
            recorded_at=recorded_at or self._clock.now(),
            photo_path=photo_path,
        )
        self._events.append(event)
        return event

    def events_of(self, employee_id: int, day: date) -> list[AttendanceEvent]:
        rows = [e for e in self._events if e.employee_id == employee_id and e.recorded_at.date() == day]
        return sorted(rows, key=lambda e: e.recorded_at)

    def renumber(self) -> None:
        # เรียงตามเวลาแล้วกำหนด id ใหม่ ใช้หลัง seed ข้อมูลย้อนหลัง
        self._events.sort(key=lambda e: e.recorded_at)
        for i, event in enumerate(self._events, start=1):
            event.id = i


def default_employees() -> list[Employee]:
    return [
        Employee(1, "สมชาย ใจดี", "worker", True),
        Employee(2, "สมหญิง รักงาน", "worker", True),
        Employee(3, "วิชัย ตั้งใจ", "worker", True),
        Employee(4, "มานี มีสุข", "worker", True),
        Employee(5, "ปรีชา ลาออกแล้ว", "worker", False),
    ]


# ---------- ข้อมูลเดโม ----------

class DemoSeeder:
    # รูปแบบวันทำงาน (เวลาเข้า, เวลาออก) หลายรอบได้ — ครอบคลุม OK / SHORT / INCOMPLETE
    PATTERNS = [
        [("08:02", "17:05")],                      # OK
        [("09:15", "16:20")],                      # SHORT
        [("08:00", "12:01"), ("13:02", "17:30")],  # OK 2 รอบ
        [("08:10", None)],                         # INCOMPLETE ลืมกดออก
        [("07:55", "12:00"), ("13:00", "15:45")],  # SHORT 2 รอบ
    ]

    def __init__(self, employees: EmployeeRepository, attendance: AttendanceRepository, clock: ServerClock, upload_dir: Path):
        self._employees = employees
        self._attendance = attendance
        self._clock = clock
        self._upload_dir = upload_dir

    def seed(self) -> None:
        self._upload_dir.mkdir(exist_ok=True)
        today = self._clock.today()
        self._seed_past_week(today)
        self._seed_today(today)
        self._seed_expired_photos(today)
        self._attendance.renumber()

    def _placeholder_photo(self, filename: str, label: str, hue: int) -> None:
        # รูปแทนรูปถ่ายจริง (SVG) ให้หน้าเจ้านายมีอะไรให้ดู
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="480" height="640" viewBox="0 0 480 640">
<rect width="480" height="640" fill="hsl({hue},30%,82%)"/>
<circle cx="240" cy="250" r="110" fill="hsl({hue},25%,62%)"/>
<rect x="90" y="390" width="300" height="260" rx="150" fill="hsl({hue},25%,62%)"/>
<text x="240" y="600" font-family="sans-serif" font-size="28" text-anchor="middle" fill="#1A2747">{label}</text>
</svg>"""
        (self._upload_dir / filename).write_text(svg, encoding="utf-8")

    def _seed_past_week(self, today: date) -> None:
        workers = self._employees.list_all()
        workers = [e for e in workers if e.is_active]
        for days_ago in range(7, 0, -1):
            day = today - timedelta(days=days_ago)
            for i, emp in enumerate(workers):
                if (days_ago + i) % 6 == 0:
                    continue  # บางวันไม่มาทำงาน
                for t_in, t_out in self.PATTERNS[(days_ago + i) % len(self.PATTERNS)]:
                    for type_, hhmm in (("in", t_in), ("out", t_out)):
                        if hhmm is None:
                            continue
                        at = datetime.combine(day, time.fromisoformat(hhmm), BKK)
                        name = f"seed_{emp.id}_{day:%Y%m%d}_{hhmm.replace(':', '')}.svg"
                        self._placeholder_photo(name, f"{emp.name} {hhmm}", 200 + emp.id * 30)
                        self._attendance.add(emp.id, type_, name, at)

    def _seed_today(self, today: date) -> None:
        # วันนี้: วิชัย ทำไปแล้ว 1 รอบ (SHORT), สมชาย เข้างานอยู่ (INCOMPLETE)
        # สมหญิง กับ มานี ยังไม่ลงเวลา — ไว้เดโมการกดเข้างานจากหน้าพนักงาน
        current = self._clock.now()
        for emp_id, offsets in ((3, (-300, -60)), (1, (-200, None))):
            for type_, minutes in zip(("in", "out"), offsets):
                if minutes is None:
                    continue
                at = current + timedelta(minutes=minutes)
                if at.date() != today:
                    continue  # ถ้าเปิดเดโมตอนเช้ามืด เวลาจะตกไปเมื่อวาน — ข้าม
                name = f"seed_{emp_id}_today_{type_}.svg"
                self._placeholder_photo(name, f"วันนี้ {at:%H:%M}", 200 + emp_id * 30)
                self._attendance.add(emp_id, type_, name, at)

    def _seed_expired_photos(self, today: date) -> None:
        # รายการเก่าเกิน 1 ปี — รูปถูกลบตามนโยบาย D8 (ไฟล์ไม่มีจริง) ไว้เดโม "ไม่พบรูป"
        old_day = today - timedelta(days=400)
        self._attendance.add(1, "in", "deleted_old_in.jpg", datetime.combine(old_day, time(8, 0), BKK))
        self._attendance.add(1, "out", "deleted_old_out.jpg", datetime.combine(old_day, time(17, 0), BKK))
