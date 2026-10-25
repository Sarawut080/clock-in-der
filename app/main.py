from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import errors
from .container import Container
from .routers.clock import ClockRouter
from .routers.report import ReportRouter

# NFR6 (เวลาไทย) จัดการใน mock_store.BKK — ตอนใช้ Docker จริงให้ตั้ง TZ=Asia/Bangkok ใน compose
BASE = Path(__file__).resolve().parent


class ClockInApp:
    def __init__(self, container: Container | None = None):
        self.container = container or Container()
        self.app = FastAPI(title="ระบบบันทึกเข้า-ออกงานด้วยรูปถ่าย (mockup)", lifespan=self._lifespan)
        self._register_routes()
        self._mount_static()

    @asynccontextmanager
    async def _lifespan(self, _: FastAPI):
        self.container.seeder.seed()
        yield

    def _register_routes(self) -> None:
        errors.register(self.app)
        self.app.include_router(ClockRouter(self.container.clock_service).router)
        self.app.include_router(ReportRouter(self.container.report_service).router)
        self.app.add_api_route("/", self.worker_page, methods=["GET"], include_in_schema=False)
        self.app.add_api_route("/boss", self.boss_page, methods=["GET"], include_in_schema=False)

    def _mount_static(self) -> None:
        upload_dir = self.container.upload_dir
        upload_dir.mkdir(exist_ok=True)
        self.app.mount("/photos", StaticFiles(directory=upload_dir), name="photos")
        self.app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

    def worker_page(self):
        return FileResponse(BASE / "static" / "worker.html")

    def boss_page(self):
        return FileResponse(BASE / "static" / "boss.html")


app = ClockInApp().app
