import pytest

from app.auth import (
    AuthService,
    LoginThrottle,
    MAX_FAILURES,
    LOCK_SECONDS,
    PinHasher,
    RateLimiter,
    SessionStore,
    SESSION_SECONDS,
    clean_name,
)
from app.errors import ApiError
from app.mock_store import InMemoryEmployeeRepository


class Ticker:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def test_hash_is_salted_and_verifies():
    h = PinHasher()
    a, b = h.hash("123456"), h.hash("123456")
    assert a != b  # salt สุ่ม
    assert h.verify("123456", a) and not h.verify("123457", a)
    assert not h.verify("123456", None) and not h.verify("123456", "")


def test_throttle_locks_after_max_failures_then_expires():
    now = Ticker()
    t = LoginThrottle(now)
    for _ in range(MAX_FAILURES - 1):
        t.record_failure(1)
        assert not t.is_locked(1)
    t.record_failure(1)
    assert t.is_locked(1) and not t.is_locked(2)
    now.t += LOCK_SECONDS - 1
    assert t.is_locked(1)
    now.t += 2
    assert not t.is_locked(1)
    t.record_failure(1)  # นับใหม่จาก 0 หลังปลดล็อก
    assert not t.is_locked(1)


def test_throttle_reset_on_success():
    t = LoginThrottle(Ticker())
    for _ in range(MAX_FAILURES - 1):
        t.record_failure(1)
    t.reset(1)
    t.record_failure(1)
    assert not t.is_locked(1)


def test_rate_limiter_sliding_window():
    now = Ticker()
    r = RateLimiter(limit=3, window_seconds=60, now=now)
    for _ in range(3):
        assert not r.blocked("ip")
        r.record("ip")
    assert r.blocked("ip") and not r.blocked("other")
    now.t += 61
    assert not r.blocked("ip")


def test_session_expires_and_is_purged():
    now = Ticker()
    s = SessionStore(now)
    old = s.create(1)
    assert s.employee_id(old) == 1
    now.t += SESSION_SECONDS + 1
    assert s.employee_id(old) is None
    s.create(2)
    assert old not in s._sessions
    assert s.employee_id(None) is None and s.employee_id("nope") is None


def test_session_destroy():
    s = SessionStore()
    tok = s.create(1)
    s.destroy(tok)
    s.destroy(tok)  # ซ้ำได้ ไม่พัง
    assert s.employee_id(tok) is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  สมชาย   ใจดี ", "สมชาย ใจดี"),
        ("ก\nข\tค", "ก ข ค"),
        ("a​b", "ab"),  # zero-width space
        ("x\x00y\x07", "xy"),
        ("​​", ""),
        (None, ""),
    ],
)
def test_clean_name(raw, expected):
    assert clean_name(raw) == expected


def make_service(**kw):
    return AuthService(InMemoryEmployeeRepository(), PinHasher(), LoginThrottle(), SessionStore(), **kw)


def test_service_ip_failed_login_limit_blocks_even_correct_pin():
    svc = make_service(failed_logins=RateLimiter(3, 600))
    seeded = svc._hasher.hash("123456")
    for name in ("หนึ่ง", "สอง", "สาม", "สี่"):  # ได้ id 1–4
        svc._employees.add(name, seeded)
    for emp_id in (1, 2, 3):  # 3 บัญชีต่างกัน คนละ 1 ครั้ง ไม่ถึงเพดานต่อบัญชี
        with pytest.raises(ApiError) as e:
            svc.login(emp_id, "000000", "1.1.1.1")
        assert e.value.code == "WRONG_PIN"
    with pytest.raises(ApiError) as e:
        svc.login(4, "123456", "1.1.1.1")  # PIN ถูก แต่ IP นี้ผิดมาเกินเพดานแล้ว
    assert e.value.code == "LOCKED"
    token, emp = svc.login(4, "123456", "2.2.2.2")  # IP อื่นไม่โดนผลกระทบ
    assert emp.id == 4 and token


def test_service_register_ip_limit():
    svc = make_service(registrations=RateLimiter(2, 600))
    svc.register("คนหนึ่ง", "123456", "123456", "9.9.9.9")
    svc.register("คนสอง", "123456", "123456", "9.9.9.9")
    with pytest.raises(ApiError) as e:
        svc.register("คนสาม", "123456", "123456", "9.9.9.9")
    assert e.value.code == "TOO_MANY_REQUESTS"
    svc.register("คนสาม", "123456", "123456", "8.8.8.8")
