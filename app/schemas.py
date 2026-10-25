# รูปแบบข้อมูลที่ API ส่งออก — ชื่อ field ตรงกับ 02-contract.md ข้อ 2 ทุกตัว ห้ามเปลี่ยนเอง
from typing import Literal, Optional

from pydantic import BaseModel


class Employee(BaseModel):
    id: int
    name: str


class RegisterBody(BaseModel):
    name: str
    pin: str
    pin_confirm: str


class LoginBody(BaseModel):
    employee_id: int
    pin: str


class Me(BaseModel):
    employee_id: int
    name: str


class Event(BaseModel):
    id: int
    type: Literal["in", "out"]
    recorded_at: str  # ISO 8601 มี +07:00 ต่อท้าย
    photo_path: str   # ชื่อไฟล์ เปิดดูที่ /photos/<photo_path>


class ClockResult(BaseModel):
    ok: bool = True
    id: int
    type: Literal["in", "out"]
    recorded_at: str


class MeToday(BaseModel):
    employee_id: int
    name: str
    last_type: Optional[Literal["in", "out"]]
    worked_minutes: int   # นาที ไม่ใช่ชั่วโมง (นับเฉพาะรอบที่ออกงานแล้ว)
    is_complete: bool     # False = มีรอบที่เข้างานแล้วแต่ยังไม่ออก
    events: list[Event]


class ReportRow(BaseModel):
    employee_id: int
    name: str
    first_in: Optional[str]   # "HH:MM"
    last_out: Optional[str]   # "HH:MM" หรือ null ถ้ายังไม่ออกงาน
    worked_minutes: int
    status: Literal["OK", "SHORT", "INCOMPLETE"]
    events: list[Event]


class RangeRow(ReportRow):
    date: str  # "YYYY-MM-DD"
