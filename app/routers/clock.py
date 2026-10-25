# ฝั่งพนักงาน (UC1–UC4) — endpoint ตาม 02-contract.md ข้อ 2
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from .. import mock_store as store
from ..schemas import ClockResult, Employee, MeToday

router = APIRouter(prefix="/api")

ERRORS = {
    "ALREADY_CLOCKED_IN": (409, "คุณกดเข้างานไปแล้ว ยังไม่ได้กดออกงาน"),
    "NOT_CLOCKED_IN": (409, "วันนี้ยังไม่ได้เข้างาน ต้องกดเข้างานก่อนจึงจะออกงานได้"),
    "PHOTO_REQUIRED": (400, "ต้องถ่ายรูปก่อน จึงจะบันทึกเวลาได้"),
    "EMPLOYEE_NOT_FOUND": (404, "ไม่พบชื่อนี้ในรายชื่อพนักงาน เลือกชื่อใหม่อีกครั้ง"),
    # ยังไม่มีในสัญญา — ต้องเพิ่มใน 02-contract.md ก่อนใช้จริง
    "BAD_REQUEST": (400, "ข้อมูลที่ส่งมาไม่ถูกต้อง"),
}

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


def fail(code: str, message: Optional[str] = None) -> JSONResponse:
    status, default_message = ERRORS[code]
    return JSONResponse(
        status_code=status,
        content={"ok": False, "error": code, "message": message or default_message},
    )


@router.get("/employees", response_model=list[Employee])
def list_employees():
    return store.active_employees()


@router.post("/clock", response_model=ClockResult)
async def clock(
    employee_id: Optional[int] = Form(None),
    clock_type: Optional[str] = Form(None, alias="type"),  # ชื่อ field ตาม contract คือ "type"
    photo: Optional[UploadFile] = File(None),
):
    # ไม่มี field เวลาในรับเข้า — เวลามาจากเซิร์ฟเวอร์เท่านั้น (BR2)
    if clock_type not in ("in", "out"):
        return fail("BAD_REQUEST", "type ต้องเป็น in หรือ out")

    emp = store.get_employee(employee_id) if employee_id is not None else None
    if emp is None:
        return fail("EMPLOYEE_NOT_FOUND")

    content = await photo.read() if photo is not None else b""
    if not content:
        return fail("PHOTO_REQUIRED")

    # BR3 นับเฉพาะวันนี้ — ให้ตรงกับปุ่มที่หน้าเว็บแสดงจาก /api/me/today
    # ถ้าเมื่อวานลืมกดออก วันนั้นจะเป็น INCOMPLETE แต่วันนี้ยังกดเข้างานได้ตามปกติ
    today_events = store.events_of(emp["id"], store.today())
    last = today_events[-1]["type"] if today_events else None
    if clock_type == "in" and last == "in":
        return fail("ALREADY_CLOCKED_IN")
    if clock_type == "out" and last != "in":
        return fail("NOT_CLOCKED_IN")

    ext = Path(photo.filename or "").suffix.lower()
    if ext not in PHOTO_EXTENSIONS:
        ext = ".jpg"  # ไม่รับนามสกุลอื่น กันไฟล์ที่เบราว์เซอร์จะตีความเป็น HTML/SVG
    filename = f"{emp['id']}_{uuid.uuid4().hex[:12]}{ext}"
    (store.UPLOAD_DIR / filename).write_bytes(content)

    row = store.add_event(emp["id"], clock_type, filename)
    return {"ok": True, "id": row["id"], "type": row["type"], "recorded_at": store.iso(row["recorded_at"])}


@router.get("/me/today", response_model=MeToday)
def me_today(employee_id: int):
    # BR5: คืนเฉพาะข้อมูลของ employee_id ที่ขอมา
    emp = store.get_employee(employee_id)
    if emp is None:
        return fail("EMPLOYEE_NOT_FOUND")
    events = store.events_of(emp["id"], store.today())
    summary = store.summarize(events)
    return {
        "employee_id": emp["id"],
        "name": emp["name"],
        "last_type": events[-1]["type"] if events else None,
        "worked_minutes": summary["worked_minutes"],
        "is_complete": summary["is_complete"],
        "events": [store.event_out(e) for e in events],
    }
