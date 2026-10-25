"""ต่อฐานข้อมูลไม่ได้ต้องบอกสาเหตุและทางแก้ ไม่ใช่แค่ "pool หมดเวลา" — ไม่ต้องมี PostgreSQL ก็รันได้"""
import time

import pytest

from app import cli
from app.pg_store import Database


def test_refused_connection_explains_and_fails_fast():
    db = Database("postgresql://clockin:secret-pw@127.0.0.1:1/clockin")  # พอร์ต 1 ไม่มีใครฟัง
    started = time.time()
    with pytest.raises(ConnectionError) as e:
        db.open()
    assert time.time() - started < 8, "ต้องล้มเร็ว ไม่รอ pool หมดเวลา 10 วินาที"
    message = str(e.value)
    assert "DATABASE_URL" in message and "5433" in message and "5432" in message
    assert "secret-pw" not in message, "ข้อความ error ห้ามมีรหัสผ่าน"


def test_failed_open_leaves_database_reusable():
    db = Database("postgresql://clockin:x@127.0.0.1:1/clockin")
    for _ in range(2):
        with pytest.raises(ConnectionError):
            db.open()
    db.close()  # ปิดทั้งที่ไม่เคยเปิดสำเร็จ ต้องไม่พัง


def test_cli_prints_reason_without_traceback(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://clockin:secret-pw@127.0.0.1:1/clockin")
    monkeypatch.setattr("app.container.load_dotenv", lambda *_a, **_k: None)
    with pytest.raises(SystemExit) as e:
        cli.main(["init-db"])
    assert "ต่อฐานข้อมูลไม่ได้" in str(e.value) and "secret-pw" not in str(e.value)
