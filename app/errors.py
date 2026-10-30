# ข้อผิดพลาดของ API — รหัสและข้อความตาม 02-contract.md
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    CATALOG = {
        "ALREADY_CLOCKED_IN": (409, "คุณกดเข้างานไปแล้ว ยังไม่ได้กดออกงาน"),
        "NOT_CLOCKED_IN": (409, "วันนี้ยังไม่ได้เข้างาน ต้องกดเข้างานก่อนจึงจะออกงานได้"),
        "PHOTO_REQUIRED": (400, "ต้องถ่ายรูปก่อน จึงจะบันทึกเวลาได้"),
        "EMPLOYEE_NOT_FOUND": (404, "ไม่พบชื่อนี้ในรายชื่อพนักงาน เลือกชื่อใหม่อีกครั้ง"),
        # ยังไม่มีในสัญญา — ต้องเพิ่มใน 02-contract.md ก่อนใช้จริง (รหัสด้านล่างทั้งหมด)
        "BAD_REQUEST": (400, "ข้อมูลที่ส่งมาไม่ถูกต้อง"),
        "UNAUTHENTICATED": (401, "ต้องเข้าสู่ระบบก่อนใช้งาน"),
        "FORBIDDEN": (403, "ไม่มีสิทธิ์ทำรายการของคนอื่น"),
        "WRONG_PIN": (401, "PIN ไม่ถูกต้อง ลองอีกครั้ง"),
        "LOCKED": (429, "ใส่ PIN ผิดหลายครั้ง ลองใหม่ได้ในอีก 5 นาที"),
        "NAME_TAKEN": (409, "ชื่อนี้ลงทะเบียนแล้ว เข้าสู่ระบบแทน หรือใส่นามสกุลให้ต่างกัน"),
        "INVALID_NAME": (400, "ใส่ชื่อ-นามสกุลของคุณ"),
        "INVALID_PIN": (400, "ใส่ PIN เป็นตัวเลข 6 หลัก"),
        "PIN_MISMATCH": (400, "PIN 2 ช่องไม่ตรงกัน ใส่อีกครั้ง"),
        "INVALID_PHOTO": (400, "ไฟล์ที่แนบไม่ใช่รูปภาพ ถ่ายรูปใหม่อีกครั้ง"),
        "PHOTO_TOO_LARGE": (413, "รูปมีขนาดใหญ่เกินไป (ไม่เกิน 10 MB) ถ่ายรูปใหม่อีกครั้ง"),
        "TOO_MANY_REQUESTS": (429, "ทำรายการถี่เกินไป รอสักครู่แล้วลองอีกครั้ง"),
        "DAY_COMPLETE": (409, "วันนี้บันทึกเข้างานและออกงานครบแล้ว บันทึกได้วันละ 1 ครั้ง"),
    }

    def __init__(self, code: str, message: Optional[str] = None):
        self.code = code
        self.status, default_message = self.CATALOG[code]
        self.message = message or default_message
        super().__init__(self.message)

    def to_response(self) -> JSONResponse:
        return JSONResponse(
            status_code=self.status,
            content={"ok": False, "error": self.code, "message": self.message},
        )


def register(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle(_: Request, exc: ApiError) -> JSONResponse:
        return exc.to_response()

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, __: RequestValidationError) -> JSONResponse:
        # ค่าผิดชนิด/ขาด field: คืนรูปแบบ error เดียวกับสัญญา แทน {"detail": [...]} ของ FastAPI
        return ApiError("BAD_REQUEST").to_response()
