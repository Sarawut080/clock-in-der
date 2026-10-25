import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import ClockInApp
from tests.conftest import DEMO_PIN
from tests.helpers import JPEG

ISO_BKK = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+07:00$")


@pytest.fixture
def boss(client):
    assert client.post("/api/auth/login", json={"employee_id": 1, "pin": DEMO_PIN}).status_code == 200
    return client


def err(r):
    return r.json().get("error")


class TestDailyReport:
    def test_shape_matches_contract(self, boss, clock):
        yesterday = (clock.current.date() - timedelta(days=1)).isoformat()
        rows = boss.get(f"/api/report/daily?date={yesterday}").json()
        assert rows, "ข้อมูลเดโมย้อนหลังต้องมีของเมื่อวาน"
        for r in rows:
            assert set(r) == {"employee_id", "name", "first_in", "last_out", "worked_minutes", "status", "events"}
            assert r["status"] in {"OK", "SHORT", "INCOMPLETE"} and isinstance(r["worked_minutes"], int)
            assert r["worked_minutes"] >= 0
            assert r["status"] != "INCOMPLETE" or r["last_out"] is None
            for e in r["events"]:
                assert ISO_BKK.match(e["recorded_at"]) and e["type"] in {"in", "out"} and e["photo_path"]
            assert [e["recorded_at"] for e in r["events"]] == sorted(e["recorded_at"] for e in r["events"])

    def test_empty_day_returns_empty_list(self, boss):
        assert boss.get("/api/report/daily?date=2001-01-01").json() == []

    @pytest.mark.parametrize("bad", ["bad", "2026-13-01", "2026-02-30", "2026/10/24", "", "99999-01-01"])
    def test_bad_date(self, boss, bad):
        r = boss.get(f"/api/report/daily?date={bad}")
        assert r.status_code == 400 and err(r) == "BAD_REQUEST"

    def test_missing_date_uses_contract_error_format(self, boss):
        r = boss.get("/api/report/daily")
        assert r.status_code == 400 and err(r) == "BAD_REQUEST" and r.json()["ok"] is False

    def test_old_employee_history_is_still_visible(self, boss, clock):
        old = (clock.current.date() - timedelta(days=400)).isoformat()
        rows = boss.get(f"/api/report/daily?date={old}").json()
        assert [r["name"] for r in rows] == ["สมชาย ใจดี"]


class TestRangeReport:
    def test_rows_carry_date_and_filter_by_employee(self, boss, clock):
        today = clock.current.date()
        start = (today - timedelta(days=7)).isoformat()
        rows = boss.get(f"/api/report/range?from={start}&to={today.isoformat()}&employee_id=3").json()
        assert rows and {r["employee_id"] for r in rows} == {3}
        assert all(re.fullmatch(r"\d{4}-\d\d-\d\d", r["date"]) for r in rows)

    def test_unknown_employee_filter_is_empty_not_error(self, boss):
        assert boss.get("/api/report/range?from=2026-10-01&to=2026-10-02&employee_id=999").json() == []

    def test_reversed_range(self, boss):
        r = boss.get("/api/report/range?from=2026-10-10&to=2026-10-01")
        assert r.status_code == 400 and err(r) == "BAD_REQUEST"

    def test_year_limit_boundaries(self, boss):
        assert boss.get("/api/report/range?from=2025-10-25&to=2026-10-24").status_code == 200  # 365 วัน
        assert boss.get("/api/report/range?from=2026-10-25&to=2026-10-25").status_code == 200  # วันเดียว
        r = boss.get("/api/report/range?from=2025-01-01&to=2026-10-25")
        assert r.status_code == 400 and "1 ปี" in r.json()["message"]

    def test_absurd_range_is_rejected_instantly(self, boss):
        r = boss.get("/api/report/range?from=0001-01-01&to=9999-12-31")
        assert r.status_code == 400  # ไม่ใช่ค้างวนลูปหลายล้านวัน

    @pytest.mark.parametrize("q", ["from=x&to=2026-10-01", "from=2026-10-01&to=y", "from=2026-10-01", "to=2026-10-01", ""])
    def test_bad_or_missing_params(self, boss, q):
        assert err(boss.get(f"/api/report/range?{q}")) == "BAD_REQUEST"

    def test_non_numeric_employee_id(self, boss):
        r = boss.get("/api/report/range?from=2026-10-01&to=2026-10-02&employee_id=abc")
        assert r.status_code == 400 and err(r) == "BAD_REQUEST"


class TestPhotoRoute:
    def test_serves_image_to_logged_in_user(self, boss, clock):
        r = boss.get("/photos/seed_3_today_in.svg")
        assert r.status_code == 200 and b"<svg" in r.content

    def test_missing_file_is_404(self, boss):
        assert boss.get("/photos/nope.jpg").status_code == 404
        assert boss.get("/photos/deleted_old_in.jpg").status_code == 404  # รูปเกิน 1 ปีที่ถูกลบ (D8)

    @pytest.mark.parametrize(
        "path",
        ["..%2Fmain.py", "..%2F..%2Fapp%2Fmain.py", "%2e%2e%2fmain.py", "..%5Cmain.py", "....%2F%2Fmain.py", "%252e%252e%252fmain.py"],
    )
    def test_path_traversal_never_leaks_source(self, boss, path):
        r = boss.get(f"/photos/{path}")
        assert r.status_code in (400, 404) and b"ClockInApp" not in r.content

    def test_uploaded_photo_round_trip(self, boss, container):
        boss.post("/api/auth/logout")
        reg = boss.post("/api/auth/register", json={"name": "ถ่ายรูป ทดสอบ", "pin": "246810", "pin_confirm": "246810"})
        assert reg.status_code == 200
        ev = boss.post("/api/clock", data={"type": "in"}, files={"photo": ("p.jpg", JPEG, "image/jpeg")}).json()
        today = boss.get("/api/me/today").json()["events"][0]
        assert boss.get(f"/photos/{today['photo_path']}").content == JPEG
        assert ev["ok"]


class TestHeaders:
    def test_api_pages_and_photos_are_not_cacheable(self, boss):
        for url in ("/api/auth/me", "/api/employees", "/", "/boss", "/photos/seed_3_today_in.svg"):
            assert boss.get(url).headers["cache-control"] == "no-store", url

    def test_static_assets_may_be_cached(self, client):
        assert "no-store" not in client.get("/static/style.css").headers.get("cache-control", "")

    def test_security_headers_present(self, client):
        h = client.get("/login").headers
        assert h["x-content-type-options"] == "nosniff" and h["referrer-policy"] == "no-referrer"
        csp = h["content-security-policy"]
        for part in ("default-src 'self'", "object-src 'none'", "frame-ancestors 'none'", "base-uri 'self'"):
            assert part in csp
        assert "unsafe-eval" not in csp and "script-src" not in csp.replace("default-src", "")  # สคริปต์มาจาก self เท่านั้น

    def test_api_docs_keep_working(self, client):
        r = client.get("/docs")
        assert r.status_code == 200 and "content-security-policy" not in r.headers


class TestNoInlineScripts:
    """CSP ไม่อนุญาต inline script — ถ้ามีคนเพิ่ม <script> ในหน้า HTML จะพังเงียบๆ จึงตรวจที่ต้นทาง"""

    @pytest.mark.parametrize("page", ["login", "register", "worker", "boss"])
    def test_pages_only_use_external_scripts(self, client, page):
        from app.main import BASE

        html = (BASE / "static" / f"{page}.html").read_text(encoding="utf-8")
        for tag in re.findall(r"<script\b[^>]*>", html):
            assert "src=" in tag, f"{page}.html มี inline script: {tag}"
        assert not re.search(r"\son[a-z]+\s*=", html), f"{page}.html มี inline event handler"


class TestSeeder:
    def test_seed_is_idempotent_across_restarts(self, container):
        app = ClockInApp(container).app
        first = (container.employees.count(), container.attendance.count())
        for _ in range(2):  # lifespan เริ่มซ้ำ (เหมือนรีสตาร์ท) ต้องไม่เพิ่มข้อมูลเดโมซ้ำ
            with TestClient(app):
                assert (container.employees.count(), container.attendance.count()) == first
        assert first[0] == 5

    def test_demo_employees_have_stable_ids(self, container):
        assert [(e.id, e.name, e.is_active) for e in container.employees.list_all()] == [
            (1, "สมชาย ใจดี", True), (2, "สมหญิง รักงาน", True), (3, "วิชัย ตั้งใจ", True),
            (4, "มานี มีสุข", True), (5, "ปรีชา ลาออกแล้ว", False),
        ]

    def test_seed_event_ids_follow_time_order(self, boss, clock):
        today = clock.current.date()
        seen = {}
        for start, end in ((today - timedelta(days=8), today), (today - timedelta(days=401), today - timedelta(days=399))):
            for r in boss.get(f"/api/report/range?from={start}&to={end}").json():
                for e in r["events"]:
                    seen[e["id"]] = e["recorded_at"]
        by_time = [i for i, _ in sorted(seen.items(), key=lambda kv: kv[1])]
        assert by_time == sorted(by_time), "id ต้องเรียงตามเวลา (seed เพิ่มทีละรายการตามลำดับเวลา)"
        assert len(seen) >= 20


def test_unknown_routes_do_not_leak_internals(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404 and "Traceback" not in r.text
    assert client.get("/static/../app/main.py").status_code in (400, 404)
    assert b"ClockInApp" not in client.get("/static/%2e%2e/main.py").content
