from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import mock_store
from .routers import clock, report

# NFR6 (เวลาไทย) จัดการใน mock_store.BKK — ตอนใช้ Docker จริงให้ตั้ง TZ=Asia/Bangkok ใน compose
BASE = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    mock_store.seed()
    yield


app = FastAPI(title="ระบบบันทึกเข้า-ออกงานด้วยรูปถ่าย (mockup)", lifespan=lifespan)

app.include_router(clock.router)
app.include_router(report.router)


@app.get("/", include_in_schema=False)
def worker_page():
    return FileResponse(BASE / "static" / "worker.html")


@app.get("/boss", include_in_schema=False)
def boss_page():
    return FileResponse(BASE / "static" / "boss.html")


mock_store.UPLOAD_DIR.mkdir(exist_ok=True)
app.mount("/photos", StaticFiles(directory=mock_store.UPLOAD_DIR), name="photos")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
