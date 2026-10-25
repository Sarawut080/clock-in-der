# กติกาธุรกิจ (BR/D) — ไม่รู้จัก HTTP และไม่รู้ว่าข้อมูลเก็บที่ไหน
import datetime as dt
import uuid
from pathlib import Path
from typing import Optional

from .errors import ApiError
from .mock_store import AttendanceRepository, EmployeeRepository, ServerClock
from .models import AttendanceEvent, DaySummary, Employee

FULL_DAY_MINUTES = 480  # เกณฑ์ครบ 8 ชม.


class AttendanceSummarizer:
    @staticmethod
    def summarize(events: list[AttendanceEvent]) -> DaySummary:
        """จับคู่ in→out ตามลำดับเวลา แล้วรวมนาที (D2, D4)"""
        worked = 0
        open_in = None
        for ev in events:
            if ev.is_in:
                open_in = ev.recorded_at
            elif open_in is not None:
                worked += int((ev.recorded_at - open_in).total_seconds() // 60)
                open_in = None
        ins = [e.recorded_at for e in events if e.is_in]
        outs = [e.recorded_at for e in events if not e.is_in]
        incomplete = open_in is not None
        if incomplete:
            status = "INCOMPLETE"
        elif worked >= FULL_DAY_MINUTES:
            status = "OK"
        else:
            status = "SHORT"
        return DaySummary(
            first_in=ins[0].strftime("%H:%M") if ins else None,
            last_out=outs[-1].strftime("%H:%M") if outs and not incomplete else None,
            worked_minutes=worked,
            is_complete=not incomplete,
            status=status,
        )


class PhotoStorage:
    EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}

    def __init__(self, upload_dir: Path):
        self._upload_dir = upload_dir

    def save(self, employee_id: int, original_name: str, content: bytes) -> str:
        ext = Path(original_name or "").suffix.lower()
        if ext not in self.EXTENSIONS:
            ext = ".jpg"  # ไม่รับนามสกุลอื่น กันไฟล์ที่เบราว์เซอร์จะตีความเป็น HTML/SVG
        filename = f"{employee_id}_{uuid.uuid4().hex[:12]}{ext}"
        (self._upload_dir / filename).write_bytes(content)
        return filename


class ClockService:
    def __init__(self, employees: EmployeeRepository, attendance: AttendanceRepository, clock: ServerClock, photos: PhotoStorage):
        self._employees = employees
        self._attendance = attendance
        self._clock = clock
        self._photos = photos

    def list_employees(self) -> list[Employee]:
        return self._employees.list_active()

    def clock(self, employee_id: Optional[int], type_: Optional[str], photo_name: str, content: bytes) -> AttendanceEvent:
        # ไม่มี field เวลาในรับเข้า — เวลามาจากเซิร์ฟเวอร์เท่านั้น (BR2)
        if type_ not in ("in", "out"):
            raise ApiError("BAD_REQUEST", "type ต้องเป็น in หรือ out")

        emp = self._employees.get_active(employee_id) if employee_id is not None else None
        if emp is None:
            raise ApiError("EMPLOYEE_NOT_FOUND")

        if not content:
            raise ApiError("PHOTO_REQUIRED")

        # BR3 นับเฉพาะวันนี้ — ให้ตรงกับปุ่มที่หน้าเว็บแสดงจาก /api/me/today
        # ถ้าเมื่อวานลืมกดออก วันนั้นจะเป็น INCOMPLETE แต่วันนี้ยังกดเข้างานได้ตามปกติ
        today_events = self._attendance.events_of(emp.id, self._clock.today())
        last = today_events[-1].type if today_events else None
        if type_ == "in" and last == "in":
            raise ApiError("ALREADY_CLOCKED_IN")
        if type_ == "out" and last != "in":
            raise ApiError("NOT_CLOCKED_IN")

        filename = self._photos.save(emp.id, photo_name, content)
        return self._attendance.add(emp.id, type_, filename)

    def me_today(self, employee_id: int) -> dict:
        # BR5: คืนเฉพาะข้อมูลของ employee_id ที่ขอมา
        emp = self._employees.get_active(employee_id)
        if emp is None:
            raise ApiError("EMPLOYEE_NOT_FOUND")
        events = self._attendance.events_of(emp.id, self._clock.today())
        summary = AttendanceSummarizer.summarize(events)
        return {
            "employee_id": emp.id,
            "name": emp.name,
            "last_type": events[-1].type if events else None,
            "worked_minutes": summary.worked_minutes,
            "is_complete": summary.is_complete,
            "events": [e.to_api() for e in events],
        }


class ReportService:
    def __init__(self, employees: EmployeeRepository, attendance: AttendanceRepository):
        self._employees = employees
        self._attendance = attendance

    def _row(self, emp: Employee, day: dt.date) -> Optional[dict]:
        events = self._attendance.events_of(emp.id, day)
        if not events:
            return None
        s = AttendanceSummarizer.summarize(events)
        return {
            "employee_id": emp.id,
            "name": emp.name,
            "first_in": s.first_in,
            "last_out": s.last_out,
            "worked_minutes": s.worked_minutes,
            "status": s.status,
            "events": [e.to_api() for e in events],
        }

    def daily(self, day: dt.date) -> list[dict]:
        # รวมพนักงานที่ปิดใช้งานแล้วด้วย — ประวัติของคนที่ลาออกยังต้องตรวจย้อนหลังได้
        rows = (self._row(e, day) for e in self._employees.list_all())
        return [r for r in rows if r]

    def range(self, start: dt.date, end: dt.date, employee_id: Optional[int]) -> list[dict]:
        out = []
        day = start
        while day <= end:
            for emp in self._employees.list_all():
                if employee_id is not None and emp.id != employee_id:
                    continue
                row = self._row(emp, day)
                if row:
                    out.append({"date": day.isoformat(), **row})
            day += dt.timedelta(days=1)
        return out
