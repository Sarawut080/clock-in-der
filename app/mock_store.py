# ข้อมูลสมมติในหน่วยความจำ แทน PostgreSQL ชั่วคราว (mockup)
# ตอนต่อ DB จริง: เปลี่ยนเฉพาะไฟล์นี้ให้ query ตาราง employees / attendance — router กับหน้าเว็บไม่ต้องแก้
# ข้อมูลหายทุกครั้งที่รีสตาร์ทเซิร์ฟเวอร์ (ตั้งใจ — เป็นแค่ข้อมูลเดโม)
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

BKK = timezone(timedelta(hours=7))  # NFR6: เวลาไทย (ไทยไม่มี daylight saving จึงใช้ +7 ตายตัวได้)
FULL_DAY_MINUTES = 480               # เกณฑ์ครบ 8 ชม.

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"

EMPLOYEES = [
    {"id": 1, "name": "สมชาย ใจดี", "role": "worker", "is_active": True},
    {"id": 2, "name": "สมหญิง รักงาน", "role": "worker", "is_active": True},
    {"id": 3, "name": "วิชัย ตั้งใจ", "role": "worker", "is_active": True},
    {"id": 4, "name": "มานี มีสุข", "role": "worker", "is_active": True},
    {"id": 5, "name": "ปรีชา ลาออกแล้ว", "role": "worker", "is_active": False},
]

# 1 แถว = 1 เหตุการณ์ เพิ่มต่อท้ายอย่างเดียว ไม่มีแก้/ลบ (BR4)
ATTENDANCE: list[dict] = []


def now() -> datetime:
    # BR2: เวลามาจากนาฬิกาเซิร์ฟเวอร์เสมอ
    return datetime.now(BKK).replace(microsecond=0)


def today() -> date:
    return now().date()


def get_employee(employee_id: int):
    for emp in EMPLOYEES:
        if emp["id"] == employee_id and emp["is_active"]:
            return emp
    return None


def active_employees() -> list[dict]:
    # เรียงตามชื่อ ให้เมนูเลือกชื่อหาง่าย
    return sorted((e for e in EMPLOYEES if e["is_active"]), key=lambda e: e["name"])


def add_event(employee_id: int, type_: str, photo_path: str, recorded_at: datetime | None = None) -> dict:
    row = {
        "id": len(ATTENDANCE) + 1,
        "employee_id": employee_id,
        "type": type_,
        "recorded_at": recorded_at or now(),
        "photo_path": photo_path,
    }
    ATTENDANCE.append(row)
    return row


def events_of(employee_id: int, day: date) -> list[dict]:
    rows = [r for r in ATTENDANCE if r["employee_id"] == employee_id and r["recorded_at"].date() == day]
    return sorted(rows, key=lambda r: r["recorded_at"])


def iso(moment: datetime) -> str:
    # ISO 8601 มี +07:00 ต่อท้ายเสมอ (contract ข้อ 2)
    return moment.isoformat(timespec="seconds")


def summarize(events: list[dict]) -> dict:
    """จับคู่ in→out ตามลำดับเวลา แล้วรวมนาที (D2, D4)"""
    worked = 0
    open_in = None
    for ev in events:
        if ev["type"] == "in":
            open_in = ev["recorded_at"]
        elif open_in is not None:
            worked += int((ev["recorded_at"] - open_in).total_seconds() // 60)
            open_in = None
    ins = [e["recorded_at"] for e in events if e["type"] == "in"]
    outs = [e["recorded_at"] for e in events if e["type"] == "out"]
    incomplete = open_in is not None
    if incomplete:
        status = "INCOMPLETE"
    elif worked >= FULL_DAY_MINUTES:
        status = "OK"
    else:
        status = "SHORT"
    return {
        "first_in": ins[0].strftime("%H:%M") if ins else None,
        "last_out": outs[-1].strftime("%H:%M") if outs and not incomplete else None,
        "worked_minutes": worked,
        "is_complete": not incomplete,
        "status": status,
    }


def event_out(ev: dict) -> dict:
    return {
        "id": ev["id"],
        "type": ev["type"],
        "recorded_at": iso(ev["recorded_at"]),
        "photo_path": ev["photo_path"],
    }


# ---------- ข้อมูลเดโม ----------

def _placeholder_photo(filename: str, label: str, hue: int) -> None:
    # รูปแทนรูปถ่ายจริง (SVG) ให้หน้าเจ้านายมีอะไรให้ดู
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="480" height="640" viewBox="0 0 480 640">
<rect width="480" height="640" fill="hsl({hue},30%,82%)"/>
<circle cx="240" cy="250" r="110" fill="hsl({hue},25%,62%)"/>
<rect x="90" y="390" width="300" height="260" rx="150" fill="hsl({hue},25%,62%)"/>
<text x="240" y="600" font-family="sans-serif" font-size="28" text-anchor="middle" fill="#1A2747">{label}</text>
</svg>"""
    (UPLOAD_DIR / filename).write_text(svg, encoding="utf-8")


# รูปแบบวันทำงาน (เวลาเข้า, เวลาออก) หลายรอบได้ — ครอบคลุม OK / SHORT / INCOMPLETE
_PATTERNS = [
    [("08:02", "17:05")],                      # OK
    [("09:15", "16:20")],                      # SHORT
    [("08:00", "12:01"), ("13:02", "17:30")],  # OK 2 รอบ
    [("08:10", None)],                         # INCOMPLETE ลืมกดออก
    [("07:55", "12:00"), ("13:00", "15:45")],  # SHORT 2 รอบ
]


def seed() -> None:
    UPLOAD_DIR.mkdir(exist_ok=True)
    t = today()
    workers = [e for e in EMPLOYEES if e["is_active"]]

    # ย้อนหลัง 7 วัน
    for days_ago in range(7, 0, -1):
        day = t - timedelta(days=days_ago)
        for i, emp in enumerate(workers):
            if (days_ago + i) % 6 == 0:
                continue  # บางวันไม่มาทำงาน
            for t_in, t_out in _PATTERNS[(days_ago + i) % len(_PATTERNS)]:
                for type_, hhmm in (("in", t_in), ("out", t_out)):
                    if hhmm is None:
                        continue
                    at = datetime.combine(day, time.fromisoformat(hhmm), BKK)
                    name = f"seed_{emp['id']}_{day:%Y%m%d}_{hhmm.replace(':', '')}.svg"
                    _placeholder_photo(name, f"{emp['name']} {hhmm}", 200 + emp["id"] * 30)
                    add_event(emp["id"], type_, name, at)

    # วันนี้: วิชัย ทำไปแล้ว 1 รอบ (SHORT), สมชาย เข้างานอยู่ (INCOMPLETE)
    # สมหญิง กับ มานี ยังไม่ลงเวลา — ไว้เดโมการกดเข้างานจากหน้าพนักงาน
    current = now()
    for emp_id, offsets in ((3, (-300, -60)), (1, (-200, None))):
        for type_, minutes in zip(("in", "out"), offsets):
            if minutes is None:
                continue
            at = current + timedelta(minutes=minutes)
            if at.date() != t:
                continue  # ถ้าเปิดเดโมตอนเช้ามืด เวลาจะตกไปเมื่อวาน — ข้าม
            name = f"seed_{emp_id}_today_{type_}.svg"
            _placeholder_photo(name, f"วันนี้ {at:%H:%M}", 200 + emp_id * 30)
            add_event(emp_id, type_, name, at)

    # รายการเก่าเกิน 1 ปี — รูปถูกลบตามนโยบาย D8 (ไฟล์ไม่มีจริง) ไว้เดโม "ไม่พบรูป"
    old_day = t - timedelta(days=400)
    add_event(1, "in", "deleted_old_in.jpg", datetime.combine(old_day, time(8, 0), BKK))
    add_event(1, "out", "deleted_old_out.jpg", datetime.combine(old_day, time(17, 0), BKK))
    ATTENDANCE.sort(key=lambda r: r["recorded_at"])
    for i, row in enumerate(ATTENDANCE, start=1):
        row["id"] = i
