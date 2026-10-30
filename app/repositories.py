# สัญญาของชั้นเก็บข้อมูล — services/routers รู้จักแค่ไฟล์นี้ ไม่รู้ว่าข้างหลังเป็นหน่วยความจำ (mock_store) หรือ PostgreSQL (pg_store)
# เพิ่ม backend ใหม่ = เขียน 2 class นี้ให้ครบ แล้วต่อใน container.py จุดเดียว
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Optional

from .errors import ApiError
from .models import AttendanceEvent, Employee


def normalize_name(name: str) -> str:
    """รูปแบบชื่อที่ใช้เทียบซ้ำ (BR8) — ต้องตรงกับ unique index ใน db/init.sql"""
    return " ".join(name.split()).casefold()


def ensure_can_clock(type_: str, last_type: Optional[str]) -> None:
    """BR3: กดเข้าซ้ำ/ออกซ้ำไม่ได้ — last_type คือเหตุการณ์ล่าสุดของ 'วันนี้' (ลืมกดออกเมื่อวาน วันนี้ก็ยังเข้างานได้)
    วันละ 1 รอบ: ออกงานแล้ว = จบวัน กดเข้า/ออกอีกไม่ได้ (1 วันมีรูปเข้า 1 รูป ออก 1 รูป)"""
    if last_type == "out":
        raise ApiError("DAY_COMPLETE")
    if type_ == "in" and last_type == "in":
        raise ApiError("ALREADY_CLOCKED_IN")
    if type_ == "out" and last_type != "in":
        raise ApiError("NOT_CLOCKED_IN")


class EmployeeRepository(ABC):
    @abstractmethod
    def get_active(self, employee_id: int) -> Optional[Employee]: ...

    @abstractmethod
    def list_active(self) -> list[Employee]:
        """เรียงตามชื่อ ให้เมนูเลือกชื่อหาง่าย"""

    @abstractmethod
    def list_all(self) -> list[Employee]:
        """รวมคนที่ปิดใช้งานแล้ว — ประวัติของคนที่ลาออกยังต้องตรวจย้อนหลังได้"""

    @abstractmethod
    def find_by_name(self, name: str) -> Optional[Employee]: ...

    @abstractmethod
    def add(self, name: str, pin_hash: str, *, is_active: bool = True) -> Employee:
        """ชื่อซ้ำ (ตาม normalize_name) → ApiError NAME_TAKEN — ต้องตัดสินแบบ atomic แม้เรียกพร้อมกัน"""

    @abstractmethod
    def set_pin_hash(self, employee_id: int, pin_hash: str) -> None: ...

    @abstractmethod
    def count(self) -> int: ...


class AttendanceRepository(ABC):
    @abstractmethod
    def add(self, employee_id: int, type_: str, photo_path: str, recorded_at: datetime) -> AttendanceEvent:
        """เพิ่มต่อท้ายตรงๆ ไม่ตรวจกติกา BR3 — ใช้ตอน seed ข้อมูลย้อนหลังเท่านั้น (เพิ่มเรียงตามเวลา id จะเรียงตาม)"""

    @abstractmethod
    def record_checked(self, employee_id: int, type_: str, day: date, recorded_at: datetime, photo_path: str) -> AttendanceEvent:
        """ตรวจ BR3 (ensure_can_clock กับเหตุการณ์ล่าสุดของ day) แล้วบันทึก เป็นก้อนเดียวแบบ atomic ต่อพนักงาน"""

    @abstractmethod
    def events_of(self, employee_id: int, day: date) -> list[AttendanceEvent]:
        """เหตุการณ์ของวันนั้น (ตามเวลาไทย) เรียงตามเวลา"""

    @abstractmethod
    def count(self) -> int: ...
