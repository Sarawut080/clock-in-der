import hashlib
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
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
STATIC_REF = re.compile(r'((?:src|href)=")/static/([^"?#]+)(")')


class ClockInApp:
    def __init__(self, container: Container | None = None, static_dir: Path = BASE / "static"):
        self.container = container or Container.from_env()
        self.static_dir = static_dir
        self._asset_versions: dict[str, tuple[tuple[int, int], str]] = {}
        self.app = FastAPI(title="ระบบบันทึกเข้า-ออกงานด้วยรูปถ่าย (mockup)", lifespan=self._lifespan)
        self.app.middleware("http")(self._protective_headers)
        self._register_routes()
        self.app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @asynccontextmanager
    async def _lifespan(self, _: FastAPI):
        self.container.startup()  # ต่อฐานข้อมูลไม่ได้ = ล้มตั้งแต่เริ่ม ไม่ใช่ตอนผู้ใช้กดแล้วค่อยพัง
        try:
            yield
        finally:
            self.container.shutdown()

    # หน้าเว็บทั้งหมดโหลดสคริปต์/ฟอนต์/รูปจากโดเมนเดียวกัน (self) ไม่มี inline script
    # style 'unsafe-inline' ต้องมี เพราะหน้ามี <style> อยู่ในไฟล์ HTML
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
        if path.startswith("/static/"):
            # เก็บแคชได้ แต่ต้องถามเซิร์ฟเวอร์ทุกครั้ง (ไม่เปลี่ยน = 304 เร็ว) — กันเบราว์เซอร์เดาอายุแคชเองแล้วใช้ JS รุ่นเก่า
            response.headers["Cache-Control"] = "no-cache"
        else:
            response.headers["Cache-Control"] = "no-store"  # หน้า/ข้อมูล/รูปส่วนบุคคลห้ามค้างในแคช (กดย้อนกลับหลังออกจากระบบ)
        return response

    def asset_version(self, rel_path: str) -> Optional[str]:
        """8 ตัวแรกของ SHA-256 ของไฟล์ใน static — คำนวณใหม่เฉพาะเมื่อไฟล์เปลี่ยน (ดูจากเวลาแก้ไข + ขนาด)
        จึงไม่ต้องรีสตาร์ทตอนแก้ JS/CSS ระหว่างพัฒนา ส่วนตอนใช้งานจริงอ่าน stat ไม่กี่ไฟล์ต่อการเปิดหน้า"""
        path = self.static_dir / rel_path
        try:
            stat = path.stat()
        except OSError:
            return None
        key = (stat.st_mtime_ns, stat.st_size)
        cached = self._asset_versions.get(rel_path)
        if cached and cached[0] == key:
            return cached[1]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:8]
        self._asset_versions[rel_path] = (key, digest)
        return digest

    def render_page(self, name: str) -> str:
        """อ่าน HTML แล้วต่อท้าย /static/... ด้วย ?v=<hash ของไฟล์>
        เหตุ: หน้า HTML เป็น no-store จึงได้รุ่นใหม่เสมอ แต่ถ้าเบราว์เซอร์ยังถือ JS/CSS รุ่นเก่า หน้าจะเพี้ยน
        (เคยเกิดจริง: HTML ใหม่ + worker.js เก่า → ข้อความไปขึ้นตัวใหญ่ 56px) ไฟล์เปลี่ยน = URL เปลี่ยน = โหลดใหม่แน่นอน"""
        html = (self.static_dir / name).read_text(encoding="utf-8")

        def versioned(match: re.Match) -> str:
            version = self.asset_version(match[2])
            return match[0] if version is None else f"{match[1]}/static/{match[2]}?v={version}{match[3]}"

        return STATIC_REF.sub(versioned, html)

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
        return HTMLResponse(self.render_page(name))

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
