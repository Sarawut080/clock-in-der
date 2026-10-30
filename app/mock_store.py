# ข้อมูลในหน่วยความจำ — ใช้เมื่อไม่ได้ตั้ง DATABASE_URL (เดโม / ชุดทดสอบที่ไม่ต้องใช้ฐานข้อมูล)
# พฤติกรรมต้องเหมือน pg_store ทุกอย่าง: ชุดทดสอบ tests/ รันกับทั้งสองตัว
# ข้อมูลหายทุกครั้งที่รีสตาร์ทเซิร์ฟเวอร์ (ตั้งใจ — เป็นแค่ข้อมูลเดโม)
import threading
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from .errors import ApiError
from .models import AttendanceEvent, Employee
from .repositories import AttendanceRepository, EmployeeRepository, ensure_can_clock, normalize_name

BKK = timezone(timedelta(hours=7))  # NFR6: เวลาไทย (ไทยไม่มี daylight saving จึงใช้ +7 ตายตัวได้)
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"


class ServerClock:
    """BR2: เวลามาจากนาฬิกาเซิร์ฟเวอร์เสมอ"""

    def now(self) -> datetime:
        return datetime.now(BKK).replace(microsecond=0)

    def today(self) -> date:
        return self.now().date()


class InMemoryEmployeeRepository(EmployeeRepository):
    def __init__(self):
        self._employees: list[Employee] = []
        self._lock = threading.Lock()

    def get_active(self, employee_id: int) -> Optional[Employee]:
        for emp in self._employees:
            if emp.id == employee_id and emp.is_active:
                return emp
        return None

    def list_active(self) -> list[Employee]:
        return sorted((e for e in self._employees if e.is_active), key=lambda e: e.name)

    def list_all(self) -> list[Employee]:
        return list(self._employees)

    def find_by_name(self, name: str) -> Optional[Employee]:
        key = normalize_name(name)
        for emp in self._employees:
            if normalize_name(emp.name) == key:
                return emp
        return None

    def add(self, name: str, pin_hash: str, *, is_active: bool = True) -> Employee:
        with self._lock:
            if self.find_by_name(name) is not None:
                raise ApiError("NAME_TAKEN")
            emp = Employee(
                id=max((e.id for e in self._employees), default=0) + 1,
                name=name,
                role="worker",
                is_active=is_active,
                pin_hash=pin_hash,
            )
            self._employees.append(emp)
            return emp

    def set_pin_hash(self, employee_id: int, pin_hash: str) -> None:
        for emp in self._employees:
            if emp.id == employee_id:
                emp.pin_hash = pin_hash

    def count(self) -> int:
        return len(self._employees)


class InMemoryAttendanceRepository(AttendanceRepository):
    def __init__(self):
        self._events: list[AttendanceEvent] = []
        self._lock = threading.Lock()

    def _append(self, employee_id: int, type_: str, photo_path: str, recorded_at: datetime) -> AttendanceEvent:
        event = AttendanceEvent(
            id=len(self._events) + 1,
            employee_id=employee_id,
            type=type_,
            recorded_at=recorded_at,
            photo_path=photo_path,
        )
        self._events.append(event)
        return event

    def add(self, employee_id: int, type_: str, photo_path: str, recorded_at: datetime) -> AttendanceEvent:
        with self._lock:
            return self._append(employee_id, type_, photo_path, recorded_at)

    def record_checked(self, employee_id: int, type_: str, day: date, recorded_at: datetime, photo_path: str) -> AttendanceEvent:
        with self._lock:  # ตรวจ BR3 กับบันทึกต้องเป็นก้อนเดียว ไม่งั้นกดรัวๆ ผ่านพร้อมกันได้
            todays = self._events_of(employee_id, day)
            ensure_can_clock(type_, todays[-1].type if todays else None)
            return self._append(employee_id, type_, photo_path, recorded_at)

    def _events_of(self, employee_id: int, day: date) -> list[AttendanceEvent]:
        rows = [e for e in self._events if e.employee_id == employee_id and e.recorded_at.date() == day]
        return sorted(rows, key=lambda e: (e.recorded_at, e.id))

    def events_of(self, employee_id: int, day: date) -> list[AttendanceEvent]:
        return self._events_of(employee_id, day)

    def count(self) -> int:
        return len(self._events)


# ---------- ข้อมูลเดโม ----------

class DemoSeeder:
    """พนักงานเดโม 5 คน (id 1–5 ตามลำดับ) + ประวัติ 7 วัน + ของวันนี้ — ใช้ได้ทั้งหน่วยความจำและ PostgreSQL ที่ว่างเปล่า"""

    EMPLOYEES = [
        ("สมชาย ใจดี", True),
        ("สมหญิง รักงาน", True),
        ("วิชัย ตั้งใจ", True),
        ("มานี มีสุข", True),
        ("ปรีชา ลาออกแล้ว", False),
    ]

    # รูปแบบวันทำงาน (เวลาเข้า, เวลาออก) วันละ 1 รอบ — ครอบคลุม OK / SHORT / INCOMPLETE
    PATTERNS = [
        [("08:02", "17:05")],  # OK
        [("09:15", "16:20")],  # SHORT
        [("08:00", "17:30")],  # OK
        [("08:10", None)],     # INCOMPLETE ลืมกดออก
        [("07:55", "15:45")],  # SHORT
    ]

    # PIN ของพนักงานเดโมทุกคน ใช้ทดลองหน้าเข้าสู่ระบบ — คนที่ลงทะเบียนใหม่ตั้ง PIN เอง
    DEMO_PIN = "123456"

    def __init__(
        self,
        employees: EmployeeRepository,
        attendance: AttendanceRepository,
        clock: ServerClock,
        upload_dir: Path,
        hash_pin: Callable[[str], str],
    ):
        self._employees = employees
        self._attendance = attendance
        self._clock = clock
        self._upload_dir = upload_dir
        self._hash_pin = hash_pin
        self._seeded = False

    def seed(self) -> None:
        if self._seeded:
            return  # lifespan เริ่มซ้ำ (เช่นในชุดทดสอบ) ต้องไม่เพิ่มข้อมูลเดโมซ้ำ
        if self._employees.count() or self._attendance.count():
            raise RuntimeError("DemoSeeder ใช้ได้กับที่เก็บข้อมูลที่ว่างเปล่าเท่านั้น")
        self._seeded = True
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        demo_hash = self._hash_pin(self.DEMO_PIN)  # คำนวณครั้งเดียว hash ช้าโดยตั้งใจ
        workers = [self._employees.add(name, demo_hash, is_active=active) for name, active in self.EMPLOYEES]
        today = self._clock.today()
        planned: list[tuple[datetime, int, str, str]] = []  # (เวลา, พนักงาน, ประเภท, ไฟล์รูป)
        planned += self._plan_past_week(today, [w for w in workers if w.is_active])
        planned += self._plan_today(today)
        planned += self._plan_expired_photos(today)
        # เพิ่มเรียงตามเวลา — id ที่ได้ (serial ใน PostgreSQL) จึงเรียงตามเวลาโดยไม่ต้องแก้ id ย้อนหลัง
        for at, emp_id, type_, name in sorted(planned, key=lambda p: p[0]):
            self._attendance.add(emp_id, type_, name, at)

    def _placeholder_photo(self, filename: str, label: str, hue: int) -> None:
        # รูปแทนรูปถ่ายจริง (SVG) ให้หน้าเจ้านายมีอะไรให้ดู
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="480" height="640" viewBox="0 0 480 640">
<rect width="480" height="640" fill="hsl({hue},30%,82%)"/>
<circle cx="240" cy="250" r="110" fill="hsl({hue},25%,62%)"/>
<rect x="90" y="390" width="300" height="260" rx="150" fill="hsl({hue},25%,62%)"/>
<text x="240" y="600" font-family="sans-serif" font-size="28" text-anchor="middle" fill="#1A2747">{label}</text>
</svg>"""
        (self._upload_dir / filename).write_text(svg, encoding="utf-8")

    def _plan_past_week(self, today: date, workers: list[Employee]):
        planned = []
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
                        planned.append((at, emp.id, type_, name))
        return planned

    def _plan_today(self, today: date):
        # วันนี้: วิชัย ทำไปแล้ว 1 รอบ (SHORT), สมชาย เข้างานอยู่ (INCOMPLETE)
        # สมหญิง กับ มานี ยังไม่ลงเวลา — ไว้เดโมการกดเข้างานจากหน้าพนักงาน
        planned = []
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
                planned.append((at, emp_id, type_, name))
        return planned

    def _plan_expired_photos(self, today: date):
        # รายการเก่าเกิน 1 ปี — รูปถูกลบตามนโยบาย D8 (ไฟล์ไม่มีจริง) ไว้เดโม "ไม่พบรูป"
        old_day = today - timedelta(days=400)
        return [
            (datetime.combine(old_day, time(8, 0), BKK), 1, "in", "deleted_old_in.jpg"),
            (datetime.combine(old_day, time(17, 0), BKK), 1, "out", "deleted_old_out.jpg"),
        ]
