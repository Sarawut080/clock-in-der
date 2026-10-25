# ฝั่งเจ้านาย (UC5–UC7) — endpoint ตาม 02-contract.md ข้อ 2
import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..auth import AuthGuard
from ..errors import ApiError
from ..schemas import RangeRow, ReportRow
from ..services import ReportService


class ReportRouter:
    MAX_RANGE_DAYS = 366

    def __init__(self, service: ReportService, guard: AuthGuard):
        self._service = service
        # ต้องล็อกอินก่อนดูรายงาน ล็อกอินแล้วดูได้ทุกคน (ไม่แยกบทบาท)
        self.router = APIRouter(prefix="/api/report", dependencies=[Depends(guard.require)])
        self.router.add_api_route("/daily", self.daily, methods=["GET"], response_model=list[ReportRow])
        self.router.add_api_route("/range", self.range_, methods=["GET"], response_model=list[RangeRow])

    @staticmethod
    def _parse_date(value: str) -> dt.date:
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            # รหัส BAD_REQUEST ยังไม่มีในสัญญา — ต้องเพิ่มใน 02-contract.md ก่อนใช้จริง
            raise ApiError("BAD_REQUEST", "รูปแบบวันที่ไม่ถูกต้อง ใช้ YYYY-MM-DD") from None

    def daily(self, date: str):
        return self._service.daily(self._parse_date(date))

    def range_(
        self,
        from_: str = Query(alias="from"),  # contract ใช้ชื่อ query "from" ซึ่งเป็น keyword ของ Python
        to: str = Query(),
        employee_id: Optional[int] = None,  # ไม่ใส่ = ทุกคน
    ):
        start, end = self._parse_date(from_), self._parse_date(to)
        if end < start:
            raise ApiError("BAD_REQUEST", "วันที่เริ่มต้องไม่หลังวันที่สิ้นสุด")
        if (end - start).days >= self.MAX_RANGE_DAYS:
            # ไม่จำกัดช่วงจะวนทีละวันหลายล้านรอบ (0001-01-01 ถึง 9999-12-31) เซิร์ฟเวอร์ค้างได้
            raise ApiError("BAD_REQUEST", "เลือกช่วงวันที่ไม่เกิน 1 ปี")
        return self._service.range(start, end, employee_id)
