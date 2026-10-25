# ลงทะเบียน / เข้าสู่ระบบ / ออกจากระบบ — ยังไม่มีในสัญญา ต้องเพิ่มใน 02-contract.md
from fastapi import APIRouter, Request, Response

from ..auth import SESSION_COOKIE, SESSION_SECONDS, AuthGuard, AuthService
from ..models import Employee
from ..schemas import LoginBody, Me, RegisterBody


class AuthRouter:
    def __init__(self, auth: AuthService, guard: AuthGuard):
        self._auth = auth
        self._guard = guard
        self.router = APIRouter(prefix="/api/auth")
        self.router.add_api_route("/register", self.register, methods=["POST"], response_model=Me)
        self.router.add_api_route("/login", self.login, methods=["POST"], response_model=Me)
        self.router.add_api_route("/logout", self.logout, methods=["POST"])
        self.router.add_api_route("/me", self.me, methods=["GET"], response_model=Me)

    @staticmethod
    def _me(emp: Employee) -> dict:
        return {"employee_id": emp.id, "name": emp.name}

    @staticmethod
    def _set_cookie(response: Response, token: str) -> None:
        # ไม่ใส่ secure เพราะ v1 รัน HTTP ใน LAN (ดู 01-SA ข้อ 7.1)
        response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_SECONDS, httponly=True, samesite="lax", path="/")

    @staticmethod
    def _ip(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def register(self, body: RegisterBody, request: Request, response: Response):
        token, emp = self._auth.register(body.name, body.pin, body.pin_confirm, self._ip(request))
        self._set_cookie(response, token)
        return self._me(emp)

    def login(self, body: LoginBody, request: Request, response: Response):
        token, emp = self._auth.login(body.employee_id, body.pin, self._ip(request))
        self._set_cookie(response, token)
        return self._me(emp)

    def logout(self, request: Request, response: Response):
        self._auth.logout(request.cookies.get(SESSION_COOKIE))
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"ok": True}

    def me(self, request: Request):
        return self._me(self._guard.require(request))
