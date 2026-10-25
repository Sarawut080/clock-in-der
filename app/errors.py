# ข้อผิดพลาดของ API — รหัสและข้อความตาม 02-contract.md
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    CATALOG = {
        "ALREADY_CLOCKED_IN": (409, "คุณกดเข้างานไปแล้ว ยังไม่ได้กดออกงาน"),
        "NOT_CLOCKED_IN": (409, "วันนี้ยังไม่ได้เข้างาน ต้องกดเข้างานก่อนจึงจะออกงานได้"),
        "PHOTO_REQUIRED": (400, "ต้องถ่ายรูปก่อน จึงจะบันทึกเวลาได้"),
        "EMPLOYEE_NOT_FOUND": (404, "ไม่พบชื่อนี้ในรายชื่อพนักงาน เลือกชื่อใหม่อีกครั้ง"),
        # ยังไม่มีในสัญญา — ต้องเพิ่มใน 02-contract.md ก่อนใช้จริง
        "BAD_REQUEST": (400, "ข้อมูลที่ส่งมาไม่ถูกต้อง"),
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
