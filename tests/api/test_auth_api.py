import pytest

from tests.conftest import DEMO_PIN


def register(client, name="คนใหม่ ทดสอบ", pin="246810", confirm=None):
    return client.post("/api/auth/register", json={"name": name, "pin": pin, "pin_confirm": confirm or pin})


def login(client, employee_id, pin=DEMO_PIN):
    return client.post("/api/auth/login", json={"employee_id": employee_id, "pin": pin})


def assert_error(r, status, code):
    assert r.status_code == status, r.text
    body = r.json()
    assert body["ok"] is False and body["error"] == code and body["message"]


@pytest.mark.parametrize(
    "method,url",
    [
        ("get", "/api/auth/me"),
        ("get", "/api/me/today"),
        ("get", "/api/report/daily?date=2026-10-24"),
        ("get", "/api/report/range?from=2026-10-01&to=2026-10-02"),
        ("get", "/photos/seed_1_today_in.svg"),
    ],
)
def test_protected_endpoints_reject_anonymous(client, method, url):
    assert_error(getattr(client, method)(url), 401, "UNAUTHENTICATED")


def test_clock_rejects_anonymous(client):
    r = client.post("/api/clock", data={"type": "in"}, files={"photo": ("p.jpg", b"x", "image/jpeg")})
    assert_error(r, 401, "UNAUTHENTICATED")


def test_public_employee_list_hides_secrets(client):
    rows = client.get("/api/employees").json()
    assert len(rows) == 4 and all(set(r) == {"id", "name"} for r in rows)


class TestRegister:
    def test_success_sets_httponly_cookie_and_logs_in(self, client):
        r = register(client)
        assert r.status_code == 200 and r.json()["name"] == "คนใหม่ ทดสอบ"
        cookie = r.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
        assert client.get("/api/auth/me").json()["employee_id"] == r.json()["employee_id"]

    def test_new_user_can_log_in_later_with_chosen_pin(self, client):
        emp_id = register(client, pin="135790").json()["employee_id"]
        client.post("/api/auth/logout")
        assert_error(login(client, emp_id, DEMO_PIN), 401, "WRONG_PIN")
        assert login(client, emp_id, "135790").status_code == 200

    @pytest.mark.parametrize(
        "name,pin,confirm,status,code",
        [
            ("", "123456", "123456", 400, "INVALID_NAME"),
            ("   ", "123456", "123456", 400, "INVALID_NAME"),
            ("​​", "123456", "123456", 400, "INVALID_NAME"),
            ("ก" * 81, "123456", "123456", 400, "INVALID_NAME"),
            ("ทดสอบ", "12345", "12345", 400, "INVALID_PIN"),
            ("ทดสอบ", "1234567", "1234567", 400, "INVALID_PIN"),
            ("ทดสอบ", "12345a", "12345a", 400, "INVALID_PIN"),
            ("ทดสอบ", "１２３４５６", "１２３４５６", 400, "INVALID_PIN"),  # เลขเต็มความกว้าง ไม่ใช่ 0-9
            ("ทดสอบ", "", "", 400, "INVALID_PIN"),
            ("ทดสอบ", "123456", "123457", 400, "PIN_MISMATCH"),
            ("สมชาย ใจดี", "123456", "123456", 409, "NAME_TAKEN"),
            ("  สมชาย    ใจดี  ", "123456", "123456", 409, "NAME_TAKEN"),
        ],
    )
    def test_validation(self, client, name, pin, confirm, status, code):
        assert_error(register(client, name, pin, confirm), status, code)
        assert client.get("/api/auth/me").status_code == 401  # ไม่ได้ session จากการลงทะเบียนที่ล้ม

    def test_name_whitespace_and_control_chars_are_cleaned(self, client):
        r = register(client, "  ผู้ใช้\n\tใหม่​ ")
        assert r.json()["name"] == "ผู้ใช้ ใหม่"

    def test_duplicate_after_cleaning_is_rejected(self, client):
        assert register(client, "ซ้ำ ชื่อ").status_code == 200
        client.post("/api/auth/logout")
        assert_error(register(client, "ซ้ำ​ ชื่อ"), 409, "NAME_TAKEN")

    def test_pin_is_never_returned_or_stored_plain(self, client, container):
        r = register(client, pin="987654")
        assert "987654" not in r.text and "pin" not in r.json()
        emp = container.employees.find_by_name("คนใหม่ ทดสอบ")
        assert emp.pin_hash and "987654" not in emp.pin_hash

    def test_per_ip_rate_limit(self, client):
        for i in range(5):
            assert register(client, f"คนที่ {i}").status_code == 200
            client.post("/api/auth/logout")
        assert_error(register(client, "คนที่ 99"), 429, "TOO_MANY_REQUESTS")


class TestLogin:
    def test_demo_user_logs_in(self, client):
        r = login(client, 2)
        assert r.status_code == 200 and r.json() == {"employee_id": 2, "name": "สมหญิง รักงาน"}

    def test_wrong_pin_then_right_pin(self, client):
        assert_error(login(client, 2, "000000"), 401, "WRONG_PIN")
        assert client.get("/api/auth/me").status_code == 401
        assert login(client, 2).status_code == 200

    @pytest.mark.parametrize("pin", ["", "12", "abcdef", "1234567"])
    def test_malformed_pin(self, client, pin):
        assert_error(login(client, 2, pin), 400, "INVALID_PIN")

    def test_unknown_and_inactive_employee(self, client):
        assert_error(login(client, 99), 404, "EMPLOYEE_NOT_FOUND")
        assert_error(login(client, 5), 404, "EMPLOYEE_NOT_FOUND")  # ปรีชา ลาออกแล้ว

    def test_lockout_after_five_failures_blocks_right_pin_too(self, client):
        results = [login(client, 4, "000000") for _ in range(5)]
        assert [r.status_code for r in results] == [401, 401, 401, 401, 429]
        assert results[-1].json()["error"] == "LOCKED"
        assert_error(login(client, 4), 429, "LOCKED")
        assert login(client, 3).status_code == 200  # บัญชีอื่นไม่ถูกลูกหลง

    def test_successful_login_resets_failure_count(self, client):
        for _ in range(4):
            login(client, 4, "000000")
        assert login(client, 4).status_code == 200
        client.post("/api/auth/logout")
        for _ in range(4):
            assert login(client, 4, "000000").status_code == 401  # นับใหม่ ยังไม่ล็อก

    def test_missing_or_mistyped_fields_use_contract_error_format(self, client):
        for body in ({}, {"employee_id": "abc", "pin": "123456"}, {"pin": "123456"}, {"employee_id": 1}):
            assert_error(client.post("/api/auth/login", json=body), 400, "BAD_REQUEST")
        assert_error(client.post("/api/auth/login", content="not json", headers={"Content-Type": "application/json"}), 400, "BAD_REQUEST")


class TestLogout:
    def test_logout_invalidates_session(self, client):
        login(client, 1)
        stale = client.cookies.get("clockin_session")
        assert client.post("/api/auth/logout").json() == {"ok": True}
        assert_error(client.get("/api/auth/me"), 401, "UNAUTHENTICATED")
        client.cookies.set("clockin_session", stale)  # cookie เก่าต้องใช้ไม่ได้แม้ถูกขโมยไปเก็บ
        assert_error(client.get("/api/auth/me"), 401, "UNAUTHENTICATED")

    def test_logout_without_session_is_harmless(self, client):
        assert client.post("/api/auth/logout").status_code == 200

    def test_forged_cookie_rejected(self, client):
        client.cookies.set("clockin_session", "A" * 43)
        assert_error(client.get("/api/auth/me"), 401, "UNAUTHENTICATED")


class TestPageGuards:
    def test_anonymous_is_redirected_to_login(self, client):
        for url in ("/", "/boss"):
            r = client.get(url)
            assert r.status_code == 302 and r.headers["location"] == "/login"

    def test_auth_pages_open_when_anonymous(self, client):
        for url in ("/login", "/register"):
            assert client.get(url).status_code == 200

    def test_signed_in_user_skips_auth_pages_and_sees_app(self, client):
        login(client, 1)
        for url in ("/login", "/register"):
            r = client.get(url)
            assert r.status_code == 302 and r.headers["location"] == "/"
        assert client.get("/").status_code == 200 and client.get("/boss").status_code == 200
