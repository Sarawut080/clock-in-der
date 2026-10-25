# ฝั่งพนักงาน (UC1–UC4) — endpoint ตาม 02-contract.md ข้อ 2
from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile

from ..schemas import ClockResult, Employee, MeToday
from ..services import ClockService


class ClockRouter:
    def __init__(self, service: ClockService):
        self._service = service
        self.router = APIRouter(prefix="/api")
        self.router.add_api_route("/employees", self.list_employees, methods=["GET"], response_model=list[Employee])
        self.router.add_api_route("/clock", self.clock, methods=["POST"], response_model=ClockResult)
        self.router.add_api_route("/me/today", self.me_today, methods=["GET"], response_model=MeToday)

    def list_employees(self):
        return [e.to_api() for e in self._service.list_employees()]

    async def clock(
        self,
        employee_id: Optional[int] = Form(None),
        clock_type: Optional[str] = Form(None, alias="type"),  # ชื่อ field ตาม contract คือ "type"
        photo: Optional[UploadFile] = File(None),
    ):
        content = await photo.read() if photo is not None else b""
        photo_name = (photo.filename if photo is not None else "") or ""
        event = self._service.clock(employee_id, clock_type, photo_name, content)
        return {
            "ok": True,
            "id": event.id,
            "type": event.type,
            "recorded_at": event.to_api()["recorded_at"],
        }

    def me_today(self, employee_id: int):
        return self._service.me_today(employee_id)
