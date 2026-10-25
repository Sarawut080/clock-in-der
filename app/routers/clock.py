# ฝั่งพนักงาน (UC1–UC4) — endpoint ตาม 02-contract.md ข้อ 2
from typing import Optional

from fastapi import APIRouter, File, Form, Request, UploadFile

from ..auth import AuthGuard
from ..errors import ApiError
from ..schemas import ClockResult, Employee, MeToday
from ..services import ClockService, PhotoStorage


class ClockRouter:
    def __init__(self, service: ClockService, guard: AuthGuard):
        self._service = service
        self._guard = guard
        self.router = APIRouter(prefix="/api")
        self.router.add_api_route("/employees", self.list_employees, methods=["GET"], response_model=list[Employee])
        self.router.add_api_route("/clock", self.clock, methods=["POST"], response_model=ClockResult)
        self.router.add_api_route("/me/today", self.me_today, methods=["GET"], response_model=MeToday)

    def _own_id(self, request: Request, requested: Optional[int]) -> int:
        # BR5: ทำรายการได้เฉพาะของตนเอง — employee_id มาจาก session ถ้าส่งมาต้องตรงกัน
        emp = self._guard.require(request)
        if requested is not None and requested != emp.id:
            raise ApiError("FORBIDDEN")
        return emp.id

    @staticmethod
    async def _read_limited(photo: Optional[UploadFile]) -> bytes:
        # อ่านทีละก้อนแล้วหยุดทันทีที่เกินเพดาน ไม่ดึงไฟล์ใหญ่ทั้งก้อนเข้าแรม
        if photo is None:
            return b""
        content = bytearray()
        while chunk := await photo.read(64 * 1024):
            content += chunk
            if len(content) > PhotoStorage.MAX_BYTES:
                raise ApiError("PHOTO_TOO_LARGE")
        return bytes(content)

    def list_employees(self):
        # เปิดให้ไม่ต้องล็อกอิน: หน้าเข้าสู่ระบบใช้เลือกชื่อ
        return [e.to_api() for e in self._service.list_employees()]

    async def clock(
        self,
        request: Request,
        employee_id: Optional[int] = Form(None),
        clock_type: Optional[str] = Form(None, alias="type"),  # ชื่อ field ตาม contract คือ "type"
        photo: Optional[UploadFile] = File(None),
    ):
        own_id = self._own_id(request, employee_id)
        content = await self._read_limited(photo)
        event = self._service.clock(own_id, clock_type, content)
        return {
            "ok": True,
            "id": event.id,
            "type": event.type,
            "recorded_at": event.to_api()["recorded_at"],
        }

    def me_today(self, request: Request, employee_id: Optional[int] = None):
        return self._service.me_today(self._own_id(request, employee_id))
