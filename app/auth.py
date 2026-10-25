# ล็อกอินด้วยชื่อ + PIN 6 หลัก — ใช้เฉพาะ stdlib
# session และตัวนับการใส่ผิดอยู่ในหน่วยความจำ รีสตาร์ทเซิร์ฟเวอร์แล้วต้องล็อกอินใหม่ (เหมือนข้อมูล mock อื่น)
import hashlib
import hmac
import re
import secrets
import threading
import time
from typing import Callable, Optional

from fastapi import Request

from .errors import ApiError
from .models import Employee
from .repositories import EmployeeRepository

SESSION_COOKIE = "clockin_session"
SESSION_SECONDS = 30 * 24 * 3600
MAX_FAILURES = 5
LOCK_SECONDS = 5 * 60
# จำกัดต่อ IP เพิ่มจากการล็อกต่อบัญชี: กันคนเดียวไล่ล็อกทุกบัญชี และกันสแปมลงทะเบียน
IP_WINDOW_SECONDS = 10 * 60
IP_MAX_FAILED_LOGINS = 20
IP_MAX_REGISTRATIONS = 5
PIN_PATTERN = re.compile(r"[0-9]{6}")


def clean_name(raw: Optional[str]) -> str:
    """ตัดอักขระควบคุม/อักขระมองไม่เห็น (ขึ้นบรรทัดใหม่, zero-width) และยุบช่องว่างซ้ำ"""
    printable = "".join(ch for ch in (raw or "") if ch.isprintable() or ch.isspace())
    return " ".join(printable.split())


class PinHasher:
    ROUNDS = 200_000

    def hash(self, pin: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, self.ROUNDS)
        return f"{salt.hex()}${digest.hex()}"

    def verify(self, pin: str, stored: Optional[str]) -> bool:
        if not stored:
            return False
        salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt_hex), self.ROUNDS)
        return hmac.compare_digest(digest.hex(), digest_hex)


class LoginThrottle:
    """ใส่ PIN ผิดครบ MAX_FAILURES ครั้ง ล็อกบัญชีนั้น LOCK_SECONDS วินาที"""

    def __init__(self, now: Callable[[], float] = time.time):
        self._now = now
        self._lock = threading.Lock()
        self._failures: dict[int, int] = {}
        self._locked_until: dict[int, float] = {}

    def is_locked(self, employee_id: int) -> bool:
        with self._lock:
            until = self._locked_until.get(employee_id)
            if until is None:
                return False
            if self._now() >= until:
                del self._locked_until[employee_id]
                self._failures.pop(employee_id, None)
                return False
            return True

    def record_failure(self, employee_id: int) -> None:
        with self._lock:
            count = self._failures.get(employee_id, 0) + 1
            self._failures[employee_id] = count
            if count >= MAX_FAILURES:
                self._locked_until[employee_id] = self._now() + LOCK_SECONDS

    def reset(self, employee_id: int) -> None:
        with self._lock:
            self._failures.pop(employee_id, None)
            self._locked_until.pop(employee_id, None)


class RateLimiter:
    """นับเหตุการณ์ต่อ key ในหน้าต่างเวลาเลื่อน — เต็ม limit แล้ว blocked() เป็นจริงจนกว่าเหตุการณ์เก่าจะหลุดหน้าต่าง"""

    def __init__(self, limit: int, window_seconds: float, now: Callable[[], float] = time.time):
        self._limit = limit
        self._window = window_seconds
        self._now = now
        self._lock = threading.Lock()
        self._hits: dict[str, list[float]] = {}

    def _recent(self, key: str) -> list[float]:
        cutoff = self._now() - self._window
        hits = [t for t in self._hits.get(key, []) if t > cutoff]
        if hits:
            self._hits[key] = hits
        else:
            self._hits.pop(key, None)
        return hits

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key)) >= self._limit

    def record(self, key: str) -> None:
        with self._lock:
            self._recent(key)
            self._hits.setdefault(key, []).append(self._now())


class SessionStore:
    def __init__(self, now: Callable[[], float] = time.time):
        self._now = now
        self._sessions: dict[str, tuple[int, float]] = {}

    def create(self, employee_id: int) -> str:
        now = self._now()
        # ล้างตัวที่หมดอายุทุกครั้งที่สร้างใหม่ ไม่ให้ค้างในหน่วยความจำ
        for stale in [t for t, (_, exp) in self._sessions.items() if exp <= now]:
            del self._sessions[stale]
        token = secrets.token_urlsafe(32)
        self._sessions[token] = (employee_id, now + SESSION_SECONDS)
        return token

    def employee_id(self, token: Optional[str]) -> Optional[int]:
        if not token:
            return None
        entry = self._sessions.get(token)
        if entry is None:
            return None
        employee_id, expires = entry
        if self._now() >= expires:
            del self._sessions[token]
            return None
        return employee_id

    def destroy(self, token: Optional[str]) -> None:
        if token:
            self._sessions.pop(token, None)


class AuthService:
    def __init__(
        self,
        employees: EmployeeRepository,
        hasher: PinHasher,
        throttle: LoginThrottle,
        sessions: SessionStore,
        failed_logins: Optional[RateLimiter] = None,
        registrations: Optional[RateLimiter] = None,
    ):
        self._employees = employees
        self._hasher = hasher
        self._throttle = throttle
        self._sessions = sessions
        self._failed_logins = failed_logins or RateLimiter(IP_MAX_FAILED_LOGINS, IP_WINDOW_SECONDS)
        self._registrations = registrations or RateLimiter(IP_MAX_REGISTRATIONS, IP_WINDOW_SECONDS)
        self._register_lock = threading.Lock()  # ตรวจชื่อซ้ำ + เพิ่มบัญชี ต้องเป็นก้อนเดียว ไม่งั้นส่งพร้อมกันได้ 2 บัญชีชื่อเดียวกัน

    def register(self, name: str, pin: str, pin_confirm: str, client_ip: str = "unknown") -> tuple[str, Employee]:
        if self._registrations.blocked(client_ip):
            raise ApiError("TOO_MANY_REQUESTS")
        clean = clean_name(name)
        if not clean or len(clean) > 80:
            raise ApiError("INVALID_NAME")
        if not PIN_PATTERN.fullmatch(pin or ""):
            raise ApiError("INVALID_PIN")
        if pin != pin_confirm:
            raise ApiError("PIN_MISMATCH")
        if self._employees.find_by_name(clean) is not None:
            raise ApiError("NAME_TAKEN")  # ปฏิเสธก่อนคำนวณ hash ที่ช้า
        pin_hash = self._hasher.hash(pin)  # ช้าโดยตั้งใจ ทำนอก lock
        with self._register_lock:
            if self._employees.find_by_name(clean) is not None:  # ตรวจซ้ำ: อาจมีคนลงชื่อเดียวกันระหว่างรอ hash
                raise ApiError("NAME_TAKEN")
            emp = self._employees.add(clean, pin_hash)
        # นับเฉพาะที่สร้างบัญชีสำเร็จ — คนพิมพ์ผิดหลายครั้งไม่ถูกล็อกเอง แต่สแปมสร้างบัญชีถูกจำกัด
        self._registrations.record(client_ip)
        return self._sessions.create(emp.id), emp

    def login(self, employee_id: Optional[int], pin: str, client_ip: str = "unknown") -> tuple[str, Employee]:
        emp = self._employees.get_active(employee_id) if employee_id is not None else None
        if emp is None:
            raise ApiError("EMPLOYEE_NOT_FOUND")
        if self._throttle.is_locked(emp.id) or self._failed_logins.blocked(client_ip):
            raise ApiError("LOCKED")
        if not PIN_PATTERN.fullmatch(pin or ""):
            raise ApiError("INVALID_PIN")
        if not self._hasher.verify(pin, emp.pin_hash):
            self._throttle.record_failure(emp.id)
            self._failed_logins.record(client_ip)
            if self._throttle.is_locked(emp.id):
                raise ApiError("LOCKED")
            raise ApiError("WRONG_PIN")
        self._throttle.reset(emp.id)
        return self._sessions.create(emp.id), emp

    def logout(self, token: Optional[str]) -> None:
        self._sessions.destroy(token)

    def current(self, token: Optional[str]) -> Optional[Employee]:
        employee_id = self._sessions.employee_id(token)
        return self._employees.get_active(employee_id) if employee_id is not None else None


class AuthGuard:
    def __init__(self, auth: AuthService):
        self._auth = auth

    def optional(self, request: Request) -> Optional[Employee]:
        return self._auth.current(request.cookies.get(SESSION_COOKIE))

    def require(self, request: Request) -> Employee:
        emp = self.optional(request)
        if emp is None:
            raise ApiError("UNAUTHENTICATED")
        return emp
