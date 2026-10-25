from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import errors
from .container import Container
from .errors import ApiError
from .services import PhotoStorage
from .routers.auth import AuthRouter
from .routers.clock import ClockRouter
from .routers.report import ReportRouter

# NFR6 (เวลาไทย): แอปใช้ mock_store.BKK (+07:00) และ PostgreSQL ตั้ง timezone=Asia/Bangkok ต่อ connection (pg_store.Database)
BASE = Path(__file__).resolve().parent


class ClockInApp:
    def __init__(self, container: Container | None = None):
        self.container = container or Container.from_env()
        self.app = FastAPI(title="ระบบบันทึกเข้า-ออกงานด้วยรูปถ่าย (mockup)", lifespan=self._lifespan)
        self.app.middleware("http")(self._protective_headers)
        self._register_routes()
        self.app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

    @asynccontextmanager
    async def _lifespan(self, _: FastAPI):
        self.container.startup()  # ต่อฐานข้อมูลไม่ได้ = ล้มตั้งแต่เริ่ม ไม่ใช่ตอนผู้ใช้กดแล้วค่อยพัง
        try:
            yield
        finally:
            self.container.shutdown()

    # หน้าเว็บทั้งหมดโหลดสคริปต์/ฟอนต์/รูปจากโดเมนเดียวกัน (self) ไม่มี inline script
    # style 'unsafe-inline' ต้องมี เพราะหน้ามี <style> ในไฟล์ HTML และ JS ตั้ง style ความกว้างเทปชั่วโมง
    CSP = (
        "default-src 'self'; img-src 'self' blob:; style-src 'self' 'unsafe-inline'; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )
    DOC_PATHS = ("/docs", "/redoc", "/openapi.json")  # Swagger UI โหลดสคริปต์จาก CDN ไม่ใส่ CSP

    async def _protective_headers(self, request: Request, call_next):
        path = request.url.path
        if request.method == "POST" and path == "/api/clock":
            # ปฏิเสธไฟล์ใหญ่จากหัว Content-Length ก่อนรับเนื้อหา (เผื่อ multipart overhead)
            length = request.headers.get("content-length", "")
            if length.isdigit() and int(length) > PhotoStorage.MAX_BYTES + 64 * 1024:
                return ApiError("PHOTO_TOO_LARGE").to_response()
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if not path.startswith(self.DOC_PATHS):
            response.headers["Content-Security-Policy"] = self.CSP
        if not path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"  # หน้า/ข้อมูล/รูปส่วนบุคคลห้ามค้างในแคช (กดย้อนกลับหลังออกจากระบบ)
        return response

    def _register_routes(self) -> None:
        c = self.container
        errors.register(self.app)
        self.app.include_router(AuthRouter(c.auth, c.guard).router)
        self.app.include_router(ClockRouter(c.clock_service, c.guard).router)
        self.app.include_router(ReportRouter(c.report_service, c.guard).router)
        # หน้าที่ต้องล็อกอิน: ไม่มี session → ไปหน้าเข้าสู่ระบบ
        self.app.add_api_route("/", self.worker_page, methods=["GET"], include_in_schema=False)
        self.app.add_api_route("/boss", self.boss_page, methods=["GET"], include_in_schema=False)
        # หน้าสำหรับคนที่ยังไม่ล็อกอิน: มี session แล้ว → ไปหน้าบันทึกเวลา
        self.app.add_api_route("/login", self.login_page, methods=["GET"], include_in_schema=False)
        self.app.add_api_route("/register", self.register_page, methods=["GET"], include_in_schema=False)
        # รูปพนักงานเป็นข้อมูลส่วนบุคคล ต้องล็อกอินก่อนดู
        self.app.add_api_route("/photos/{filename}", self.photo, methods=["GET"], include_in_schema=False)

    def _page(self, request: Request, name: str, *, needs_login: bool):
        signed_in = self.container.guard.optional(request) is not None
        if needs_login and not signed_in:
            return RedirectResponse("/login", status_code=302)
        if not needs_login and signed_in:
            return RedirectResponse("/", status_code=302)
        return FileResponse(BASE / "static" / name)

    def worker_page(self, request: Request):
        return self._page(request, "worker.html", needs_login=True)

    def boss_page(self, request: Request):
        return self._page(request, "boss.html", needs_login=True)

    def login_page(self, request: Request):
        return self._page(request, "login.html", needs_login=False)

    def register_page(self, request: Request):
        return self._page(request, "register.html", needs_login=False)

    def photo(self, request: Request, filename: str):
        self.container.guard.require(request)
        path = self.container.upload_dir / Path(filename).name  # ตัดส่วนโฟลเดอร์ กัน path traversal
        if not path.is_file():
            return Response(status_code=404)
        return FileResponse(path)


app = ClockInApp().app
