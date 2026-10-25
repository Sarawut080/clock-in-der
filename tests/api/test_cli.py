"""คำสั่งดูแลระบบ python -m app.cli — รันกับฐานข้อมูลทดสอบ (ข้ามถ้าไม่ได้ตั้ง TEST_DATABASE_URL)"""
import pytest

from app import cli
from app.container import Container
from app.pg_store import Database
from tests.conftest import NO_PG_REASON, TEST_DATABASE_URL
from tests.helpers import FakeClock

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason=NO_PG_REASON)


@pytest.fixture
def empty_db(monkeypatch, tmp_path):
    """ฐานข้อมูลทดสอบที่ว่างเปล่า + ชี้ DATABASE_URL ให้ CLI ใช้ตัวนี้ (ไม่ใช่ .env จริง)"""
    db = Database(TEST_DATABASE_URL)
    db.open()
    db.ensure_schema()
    db.truncate_all()
    db.close()
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setattr("app.container.UPLOAD_DIR", tmp_path / "uploads")  # seed-demo เขียนรูปเดโม ไม่ให้ไปเขียนใน uploads จริง
    return TEST_DATABASE_URL


def fresh(clock=None) -> Container:
    c = Container(clock=clock or FakeClock(), database=Database(TEST_DATABASE_URL), seed_demo=False)
    c.database.open()
    return c


def test_exits_with_help_when_database_url_missing(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("app.container.load_dotenv", lambda *_a, **_k: None)  # ไม่อ่าน .env จริงของเครื่องนี้
    with pytest.raises(SystemExit) as e:
        cli.main(["init-db"])
    assert "DATABASE_URL" in str(e.value)


def test_init_db_then_seed_demo_then_refuses_second_seed(empty_db, capsys):
    cli.main(["init-db"])
    cli.main(["seed-demo"])
    c = fresh()
    try:
        assert c.employees.count() == 5 and c.attendance.count() > 0
        _, emp = c.auth.login(1, "123456", "9.9.9.9")  # PIN เดโมใช้ได้
        assert emp.name == "สมชาย ใจดี"
    finally:
        c.shutdown()
    with pytest.raises(SystemExit) as e:
        cli.main(["seed-demo"])  # ฐานข้อมูลมีข้อมูลแล้ว ห้าม seed ทับ
    assert "ว่างเปล่า" in str(e.value)


def test_reset_pin_replaces_old_pin(empty_db, monkeypatch):
    cli.main(["seed-demo"])
    answers = iter(["654321", "654321"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda *_a, **_k: next(answers))
    cli.main(["reset-pin", "  สมชาย   ใจดี "])  # ชื่อพิมพ์เว้นวรรคเกินก็หาเจอ
    c = fresh()
    try:
        with pytest.raises(Exception) as old:
            c.auth.login(1, "123456", "8.8.8.8")
        assert getattr(old.value, "code", None) == "WRONG_PIN"
        assert c.auth.login(1, "654321", "8.8.8.8")[1].id == 1
    finally:
        c.shutdown()


@pytest.mark.parametrize(
    "answers,message",
    [(["12345", "12345"], "6 หลัก"), (["123456", "123457"], "ไม่ตรงกัน")],
)
def test_reset_pin_rejects_bad_input_and_keeps_old_pin(empty_db, monkeypatch, answers, message):
    cli.main(["seed-demo"])
    it = iter(answers)
    monkeypatch.setattr(cli.getpass, "getpass", lambda *_a, **_k: next(it))
    with pytest.raises(SystemExit) as e:
        cli.main(["reset-pin", "สมชาย ใจดี"])
    assert message in str(e.value)
    c = fresh()
    try:
        assert c.auth.login(1, "123456", "7.7.7.7")[1].id == 1
    finally:
        c.shutdown()


class TestWipeData:
    DB = TEST_DATABASE_URL.rsplit("/", 1)[-1].split("?")[0] if TEST_DATABASE_URL else "clockin_test"

    def counts(self):
        c = fresh()
        try:
            return c.employees.count(), c.attendance.count()
        finally:
            c.shutdown()

    @pytest.mark.parametrize("confirm", [[], ["--confirm", "clockin"], ["--confirm", ""], ["--confirm", "CLOCKIN_TEST"]])
    def test_refuses_without_exact_database_name_and_shows_what_it_would_delete(self, empty_db, confirm):
        cli.main(["seed-demo"])
        before = self.counts()
        with pytest.raises(SystemExit) as e:
            cli.main(["wipe-data", *confirm])
        assert self.DB in str(e.value) and "พนักงาน 5 คน" in str(e.value)  # บอกชัดว่าจะลบอะไรในฐานข้อมูลไหน
        assert self.counts() == before, "ยืนยันไม่ถูกต้องต้องไม่ลบอะไรเลย"

    def test_wipes_database_but_keeps_photos_by_default(self, empty_db, tmp_path):
        cli.main(["seed-demo"])
        photo = tmp_path / "uploads" / "keep.jpg"
        photo.write_bytes(b"x")
        cli.main(["wipe-data", "--confirm", self.DB])
        assert self.counts() == (0, 0)
        assert photo.exists()

    def test_photos_flag_deletes_files_but_not_folder_or_gitkeep(self, empty_db, tmp_path):
        up = tmp_path / "uploads"
        up.mkdir(exist_ok=True)
        (up / "a.jpg").write_bytes(b"x")
        (up / ".gitkeep").write_text("")
        cli.main(["wipe-data", "--confirm", self.DB, "--photos"])
        assert sorted(p.name for p in up.iterdir()) == [".gitkeep"]

    def test_ids_restart_from_one_after_wipe(self, empty_db):
        cli.main(["seed-demo"])
        cli.main(["wipe-data", "--confirm", self.DB])
        c = fresh()
        try:
            c.auth.register("คนแรกใหม่", "123456", "123456", "3.3.3.3")
            assert c.employees.find_by_name("คนแรกใหม่").id == 1
        finally:
            c.shutdown()


def test_reset_pin_unknown_name(empty_db):
    cli.main(["seed-demo"])
    with pytest.raises(SystemExit) as e:
        cli.main(["reset-pin", "ไม่มีคนนี้"])
    assert "ไม่พบ" in str(e.value)
