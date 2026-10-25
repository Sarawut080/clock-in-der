import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from app.container import Container
from app.main import ClockInApp
from app.pg_store import Database
from tests.helpers import FakeClock

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DEMO_PIN = "123456"  # PIN ของพนักงานเดโมทุกคน (DemoSeeder.DEMO_PIN)
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()
NO_PG_REASON = "ไม่ได้ตั้ง TEST_DATABASE_URL (ดู .env.example) — ข้ามชุดทดสอบบน PostgreSQL"


def make_container(backend: str, upload_dir: Path, clock) -> Container:
    """หน่วยความจำ หรือ PostgreSQL (ล้างข้อมูลก่อนทุกครั้ง; ปฏิเสธถ้าไม่ใช่ฐานข้อมูลชื่อลงท้าย _test) แล้ว startup + seed เดโม"""
    upload_dir.mkdir(parents=True, exist_ok=True)
    database = None
    if backend == "postgres":
        database = Database(TEST_DATABASE_URL)
        database.open()
        database.ensure_schema()
        database.truncate_all()
    container = Container(upload_dir=upload_dir, clock=clock, database=database)
    container.startup()
    return container


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture(params=["memory", "postgres"])
def backend(request):
    """ชุดทดสอบ api ทั้งหมดรันกับที่เก็บข้อมูลทั้งสองแบบ — สองแบบต้องตอบเหมือนกันทุกข้อ"""
    if request.param == "postgres" and not TEST_DATABASE_URL:
        pytest.skip(NO_PG_REASON)
    return request.param


@pytest.fixture
def container(tmp_path, clock, backend):
    c = make_container(backend, tmp_path / "uploads", clock)
    yield c
    c.shutdown()


@pytest.fixture
def pg_container(tmp_path, clock):
    """เฉพาะ PostgreSQL — สำหรับทดสอบสิ่งที่มีแค่ในฐานข้อมูลจริง (trigger, unique index, หลาย connection)"""
    if not TEST_DATABASE_URL:
        pytest.skip(NO_PG_REASON)
    c = make_container("postgres", tmp_path / "uploads", clock)
    yield c
    c.shutdown()


@pytest.fixture
def client(container):
    with TestClient(ClockInApp(container).app, follow_redirects=False) as c:
        yield c


@pytest.fixture
def logged_in(client):
    """ลงทะเบียนพนักงานใหม่แล้วถือ cookie ไว้ — คืน (client, employee_id)"""
    r = client.post("/api/auth/register", json={"name": "ผู้ทดสอบ ระบบ", "pin": "246810", "pin_confirm": "246810"})
    assert r.status_code == 200, r.text
    return client, r.json()["employee_id"]


@pytest.fixture(scope="session")
def live_url(tmp_path_factory):
    """เซิร์ฟเวอร์จริงบนพอร์ตสุ่ม สำหรับทดสอบผ่านเบราว์เซอร์ (ใช้ร่วมทั้งรอบ ข้อมูลสะสมต่อเนื่อง)
    ค่าเริ่มต้นใช้ข้อมูลในหน่วยความจำ — ตั้ง E2E_BACKEND=postgres เพื่อรันบน TEST_DATABASE_URL"""
    backend = "postgres" if os.environ.get("E2E_BACKEND") == "postgres" else "memory"
    if backend == "postgres" and not TEST_DATABASE_URL:
        pytest.skip(NO_PG_REASON)
    container = make_container(backend, tmp_path_factory.mktemp("uploads"), None)
    app = ClockInApp(container).app
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started:
        assert time.time() < deadline, "เซิร์ฟเวอร์ทดสอบไม่เริ่มใน 15 วินาที"
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="session")
def base_url(live_url):
    return live_url
