# โมเดลข้อมูลภายในระบบ (ไม่ใช่รูปแบบที่ API ส่งออก — อันนั้นอยู่ที่ schemas.py)
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Employee:
    id: int
    name: str
    role: str
    is_active: bool = True
    pin_hash: Optional[str] = None  # ไม่ส่งออกทาง API

    def to_api(self) -> dict:
        return {"id": self.id, "name": self.name}


@dataclass
class AttendanceEvent:
    """1 แถว = 1 เหตุการณ์ เพิ่มต่อท้ายอย่างเดียว ไม่มีแก้/ลบ (BR4)"""

    id: int
    employee_id: int
    type: str  # "in" | "out"
    recorded_at: datetime
    photo_path: str

    @property
    def is_in(self) -> bool:
        return self.type == "in"

    def to_api(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "recorded_at": self.recorded_at.isoformat(timespec="seconds"),  # ISO 8601 มี +07:00 ต่อท้ายเสมอ (contract ข้อ 2)
            "photo_path": self.photo_path,
        }


@dataclass
class DaySummary:
    first_in: Optional[str]
    last_out: Optional[str]
    worked_minutes: int  # ทางการ: นับเฉพาะรอบที่ออกงานแล้ว (D2/D4)
    is_complete: bool
    status: str  # OK | SHORT | INCOMPLETE
    open_since: Optional[datetime] = None  # เวลาเข้างานของรอบที่ยังไม่ออก (ไว้แสดงชั่วโมงสด ไม่ใช่ชั่วโมงทางการ)
