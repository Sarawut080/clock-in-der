# ฝั่งเจ้านาย (UC5–UC7) — endpoint ตาม 02-contract.md ข้อ 2
import datetime as dt
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from .. import mock_store as store
from ..schemas import RangeRow, ReportRow

router = APIRouter(prefix="/api/report")


def _row(emp: dict, day: dt.date) -> Optional[dict]:
    events = store.events_of(emp["id"], day)
    if not events:
        return None
    s = store.summarize(events)
    return {
        "employee_id": emp["id"],
        "name": emp["name"],
        "first_in": s["first_in"],
        "last_out": s["last_out"],
        "worked_minutes": s["worked_minutes"],
        "status": s["status"],
        "events": [store.event_out(e) for e in events],
    }


def _bad_request(message: str) -> JSONResponse:
    # รหัส BAD_REQUEST ยังไม่มีในสัญญา — ต้องเพิ่มใน 02-contract.md ก่อนใช้จริง
    return JSONResponse(status_code=400, content={"ok": False, "error": "BAD_REQUEST", "message": message})


def _parse_date(value: str) -> Optional[dt.date]:
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


@router.get("/daily", response_model=list[ReportRow])
def daily(date: str):
    day = _parse_date(date)
    if day is None:
        return _bad_request("รูปแบบวันที่ไม่ถูกต้อง ใช้ YYYY-MM-DD")
    # รวมพนักงานที่ปิดใช้งานแล้วด้วย — ประวัติของคนที่ลาออกยังต้องตรวจย้อนหลังได้
    rows = (_row(e, day) for e in store.EMPLOYEES)
    return [r for r in rows if r]


@router.get("/range", response_model=list[RangeRow])
def range_(
    from_: str = Query(alias="from"),  # contract ใช้ชื่อ query "from" ซึ่งเป็น keyword ของ Python
    to: str = Query(),
    employee_id: Optional[int] = None,  # ไม่ใส่ = ทุกคน
):
    start, end = _parse_date(from_), _parse_date(to)
    if start is None or end is None:
        return _bad_request("รูปแบบวันที่ไม่ถูกต้อง ใช้ YYYY-MM-DD")
    if end < start:
        return _bad_request("วันที่เริ่มต้องไม่หลังวันที่สิ้นสุด")

    out = []
    day = start
    while day <= end:
        for emp in store.EMPLOYEES:
            if employee_id is not None and emp["id"] != employee_id:
                continue
            row = _row(emp, day)
            if row:
                out.append({"date": day.isoformat(), **row})
        day += dt.timedelta(days=1)
    return out
