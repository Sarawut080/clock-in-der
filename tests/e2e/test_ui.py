"""ทดสอบผ่านเบราว์เซอร์จริง (Chromium) — มือถือ 375px / จอแคบสุด 320px / เดสก์ท็อป 1280px

screenshot เก็บไว้ที่ tests/_screenshots (ไม่ขึ้น git) ให้เปิดดูหน้าตาจริงได้
"""
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from app.mock_store import BKK
from tests.conftest import DEMO_PIN
from tests.helpers import tiny_png

pytestmark = pytest.mark.e2e

SHOTS = Path(__file__).resolve().parent.parent / "_screenshots"
PHONE = {"width": 375, "height": 812}
NARROW = {"width": 320, "height": 640}
DESKTOP = {"width": 1280, "height": 800}


@pytest.fixture
def phone(page: Page):
    page.set_viewport_size(PHONE)
    problems = []

    def on_console(m):
        # เบราว์เซอร์บันทึกคำตอบ 4xx ที่เราตั้งใจทดสอบ (PIN ผิด, รูปหาย) เป็น console error เองอยู่แล้ว — ไม่ใช่บั๊กของหน้า
        if m.type in ("error", "warning") and not m.text.startswith("Failed to load resource"):
            problems.append(f"console.{m.type}: {m.text}")

    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
    page.on("console", on_console)
    yield page
    assert problems == [], problems  # ทุกการทดสอบต้องไม่มี error/warning ในคอนโซล (รวมการละเมิด CSP)


def shot(page: Page, name: str):
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def login_as(page: Page, employee_id: int, pin: str = DEMO_PIN):
    page.goto("/login")
    page.select_option("#employee", str(employee_id))
    page.fill("#pin", pin)
    page.click("#submit")
    expect(page).to_have_url(page.url.split("/login")[0] + "/")


def pick_photo(page: Page):
    page.set_input_files("#photo", {"name": "me.png", "mimeType": "image/png", "buffer": tiny_png()})


def no_horizontal_scroll(page: Page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")


# ---------- เส้นทางหลัก ----------

def test_register_clock_in_out_dashboard_logout(phone: Page):
    name = f"ทดสอบ {uuid.uuid4().hex[:6]}"
    phone.goto("/register")
    phone.fill("#name", name)
    phone.fill("#pin", "246810")
    phone.fill("#pin-confirm", "246810")
    phone.click("#submit")

    expect(phone.locator("#employee-name")).to_have_text(name)
    expect(phone.locator("#clock-btn")).to_have_text("บันทึกเข้างาน")
    expect(phone.locator("#hours")).to_contain_text("0")

    phone.click("#clock-btn")
    expect(phone.locator("#confirm-btn")).to_be_disabled()  # BR1: ยังไม่มีรูป บันทึกไม่ได้
    pick_photo(phone)
    expect(phone.locator("#preview")).to_be_visible()
    phone.click("#confirm-btn")
    expect(phone.locator("#done")).to_be_visible()
    expect(phone.locator("#done-label")).to_have_text("บันทึกเข้างานแล้ว")
    phone.click("#done-btn")
    expect(phone.locator("#clock-btn")).to_have_text("บันทึกออกงาน")
    # กำลังนับสด: ไม่ขึ้น "ข้อมูลยังไม่ครบ" แล้ว (นั่นคือสถานะทางการในแดชบอร์ด) แต่โชว์ตัวเลขที่เดินอยู่
    expect(phone.locator("#live-badge")).to_be_visible()
    expect(phone.locator("#hours")).to_have_text(re.compile(r"^0ชม\.[01]นาที$"))

    phone.click("#clock-btn")
    pick_photo(phone)
    phone.click("#confirm-btn")
    expect(phone.locator("#done-label")).to_have_text("บันทึกออกงานแล้ว")
    phone.click("#done-btn")
    expect(phone.locator("#log li")).to_have_count(2)
    shot(phone, "worker-mobile")

    phone.click("text=ไปหน้าแดชบอร์ด")
    row = phone.locator("tr.person", has_text=name)
    expect(row).to_have_count(1)
    expect(row.locator(".badge")).to_contain_text("ไม่ครบ 8 ชม.")
    row.get_by_role("button", name="ดูรูป 2 รูป").click()
    imgs = phone.locator("tr.detail:not([hidden]) img.photo")
    expect(imgs).to_have_count(2)
    # รูปต้องโหลดและถอดรหัสได้จริง (ไม่ใช่แค่มี element) — วนเช็คเอง เพราะ wait_for_function ใช้ eval ซึ่ง CSP ของเราห้ามไว้
    for _ in range(50):
        if imgs.evaluate_all("els => els.every(i => i.complete && i.naturalWidth > 0)"):
            break
        phone.wait_for_timeout(100)
    else:
        pytest.fail("รูปในแดชบอร์ดโหลดไม่สำเร็จ")
    shot(phone, "dashboard-mobile-expanded")

    phone.click("#logout-btn")
    expect(phone).to_have_url(re.compile(r"/login$"))
    phone.goto("/boss")
    expect(phone).to_have_url(re.compile(r"/login$"))  # session ตายแล้ว เข้าแดชบอร์ดไม่ได้


def test_anonymous_visitors_are_sent_to_login(phone: Page):
    for path in ("/", "/boss"):
        phone.goto(path)
        expect(phone.get_by_role("heading", name="เข้าสู่ระบบ")).to_be_visible()


# ---------- ฟอร์มเข้าสู่ระบบ / ลงทะเบียน ----------

def test_wrong_pin_error_sits_under_field_and_keeps_focus(phone: Page):
    phone.goto("/login")
    phone.select_option("#employee", "4")
    phone.fill("#pin", "000000")
    phone.click("#submit")
    err = phone.locator("#pin-error")
    expect(err).to_contain_text("PIN ไม่ถูกต้อง ลองอีกครั้ง")
    expect(phone.locator("#pin")).to_have_attribute("aria-invalid", "true")
    expect(phone.locator("#pin")).to_be_focused()
    expect(phone.locator("#pin")).to_have_attribute("aria-describedby", "pin-error")
    shot(phone, "login-error-mobile")

    phone.fill("#pin", DEMO_PIN)
    phone.click("#submit")
    expect(phone.locator("#employee-name")).to_have_text("มานี มีสุข")


def test_login_validates_before_sending(phone: Page):
    requests = []
    phone.on("request", lambda r: requests.append(r.url) if "/api/auth/login" in r.url else None)
    phone.goto("/login")
    phone.click("#submit")
    expect(phone.locator("#employee-error")).to_have_text("เลือกชื่อของคุณ")
    expect(phone.locator("#pin-error")).to_have_text("ใส่ PIN เป็นตัวเลข 6 หลัก")
    expect(phone.locator("#employee")).to_be_focused()  # โฟกัสช่องแรกที่ผิด
    phone.select_option("#employee", "1")
    phone.fill("#pin", "12ab56")
    phone.click("#submit")
    expect(phone.locator("#employee-error")).to_have_text("")
    expect(phone.locator("#pin-error")).to_have_text("ใส่ PIN เป็นตัวเลข 6 หลัก")
    assert requests == []


def test_register_validation_messages(phone: Page):
    phone.goto("/register")
    phone.click("#submit")
    expect(phone.locator("#name-error")).to_have_text("ใส่ชื่อ-นามสกุลของคุณ")
    expect(phone.locator("#pin-error")).to_have_text("ใส่ PIN เป็นตัวเลข 6 หลัก")
    expect(phone.locator("#name")).to_be_focused()

    phone.fill("#name", "คนทดสอบ")
    phone.fill("#pin", "123456")
    phone.fill("#pin-confirm", "123457")
    phone.click("#submit")
    expect(phone.locator("#pin-confirm-error")).to_have_text("PIN 2 ช่องไม่ตรงกัน ใส่อีกครั้ง")
    expect(phone.locator("#name-error")).to_have_text("")
    expect(phone.locator("#pin-confirm")).to_be_focused()

    phone.fill("#name", "สมชาย ใจดี")  # ชื่อซ้ำกับพนักงานเดโม — เซิร์ฟเวอร์ปฏิเสธ แสดงใต้ช่องชื่อ
    phone.fill("#pin-confirm", "123456")
    phone.click("#submit")
    expect(phone.locator("#name-error")).to_contain_text("ชื่อนี้ลงทะเบียนแล้ว")
    expect(phone.locator("#name")).to_be_focused()
    shot(phone, "register-error-mobile")


def test_submit_button_blocks_double_submit(phone: Page):
    hits = []
    phone.on("request", lambda r: hits.append(1) if "/api/auth/login" in r.url else None)
    phone.route("**/api/auth/login", lambda route: (phone.wait_for_timeout(400), route.continue_()))
    phone.goto("/login")
    phone.select_option("#employee", "2")
    phone.fill("#pin", DEMO_PIN)
    phone.dblclick("#submit")
    expect(phone.locator("#employee-name")).to_be_visible()
    assert len(hits) == 1


def test_lockout_message_after_repeated_wrong_pins(phone: Page):
    phone.goto("/login")
    phone.select_option("#employee", "3")
    for _ in range(5):
        phone.fill("#pin", "000000")
        phone.click("#submit")
        expect(phone.locator("#pin-error")).not_to_have_text("")
    expect(phone.locator("#pin-error")).to_contain_text("ลองใหม่ได้ในอีก 5 นาที")


# ---------- แดชบอร์ด: ความอ่านง่ายบนมือถือ ----------

def test_dashboard_mobile_layout_is_consistent(phone: Page):
    login_as(phone, 1)
    phone.goto("/boss")
    expect(phone.locator(".kpi")).to_have_count(3)
    expect(phone.locator("tr.person").first).to_be_visible()

    tiles = phone.locator(".kpi").evaluate_all("els => els.map(e => { const r = e.getBoundingClientRect(); return [r.width, r.height]; })")
    assert max(w for w, _ in tiles) - min(w for w, _ in tiles) < 1, f"KPI กว้างไม่เท่ากัน {tiles}"
    assert max(h for _, h in tiles) - min(h for _, h in tiles) < 1, f"KPI สูงไม่เท่ากัน {tiles}"

    badge_widths = phone.locator("tr.person .badge").evaluate_all("els => els.map(e => Math.round(e.getBoundingClientRect().width))")
    assert len(set(badge_widths)) == 1, f"ป้ายสถานะกว้างไม่เท่ากัน {badge_widths}"

    # คอลัมน์ เข้างาน / ออกงาน / รวม ต้องตรงกันทุกแถว (ไม่เลื่อนตามเนื้อหา)
    for cell in ("c-in", "c-out", "c-hours"):
        xs = phone.locator(f"tr.person td.{cell}").evaluate_all("els => els.map(e => Math.round(e.getBoundingClientRect().left))")
        assert len(set(xs)) == 1, f"{cell} ไม่ตรงคอลัมน์ {xs}"

    # ป้ายกำกับเหนือค่า (ทำด้วย ::before จึงไม่อยู่ใน DOM text ต้องอ่านจาก computed style)
    labels = phone.locator("tr.person").first.locator("td[data-label]").evaluate_all(
        "els => els.map(e => getComputedStyle(e, '::before').content)")
    assert labels == ['"เข้างาน"', '"ออกงาน"', '"รวม"'], labels
    assert no_horizontal_scroll(phone)
    shot(phone, "dashboard-mobile")


def test_dashboard_sorts_attention_first(phone: Page):
    login_as(phone, 1)
    phone.goto("/boss")
    expect(phone.locator("tr.person").first).to_be_visible()
    order = phone.locator("tr.person .badge").all_inner_texts()
    rank = {"ข้อมูลยังไม่ครบ": 0, "ไม่ครบ 8 ชม.": 1, "ครบ 8 ชม.": 2}
    ranks = [rank[t.strip()] for t in order]
    assert ranks == sorted(ranks), order


def test_dashboard_kpi_counts_match_rows(phone: Page):
    login_as(phone, 1)
    phone.goto("/boss")
    expect(phone.locator("tr.person").first).to_be_visible()
    for kind, text in (("ok", "ครบ 8 ชม."), ("short", "ไม่ครบ 8 ชม."), ("incomplete", "ข้อมูลยังไม่ครบ")):
        shown = int(phone.locator(f".kpi-{kind} dd").inner_text().split()[0])
        # ตรงทั้งข้อความ ไม่งั้น "ครบ 8 ชม." จะไปนับ "ไม่ครบ 8 ชม." ด้วย
        rows = phone.locator("tr.person .badge", has_text=re.compile(rf"^\s*{re.escape(text)}\s*$")).count()
        assert shown == rows, f"{kind}: KPI {shown} แต่ในตาราง {rows}"


def test_dashboard_custom_range_validation(phone: Page):
    login_as(phone, 1)
    phone.goto("/boss")
    phone.select_option("#period", "custom")
    phone.fill("#from", "2026-10-20")
    phone.fill("#to", "2026-10-10")
    phone.click("#filters button[type=submit]")
    expect(phone.locator("#to-error")).to_have_text("วันที่สิ้นสุดต้องไม่ก่อนวันที่เริ่มต้น")
    expect(phone.locator("#to")).to_have_attribute("aria-invalid", "true")
    phone.fill("#from", "2020-01-01")
    phone.fill("#to", "2026-10-25")
    phone.click("#filters button[type=submit]")
    expect(phone.locator("#to-error")).to_have_text("เลือกช่วงวันที่ไม่เกิน 1 ปี")
    phone.fill("#from", "2026-10-01")
    phone.click("#filters button[type=submit]")
    expect(phone.locator("#to-error")).to_have_text("")
    expect(phone.locator("#result-title")).to_contain_text("ถึง")


def test_dashboard_missing_photo_shows_reason(phone: Page):
    login_as(phone, 1)
    phone.goto("/boss")
    expect(phone.locator("tr.person").first).to_be_visible()
    # รายการเกิน 1 ปีถูกลบรูปตามนโยบาย D8 (ข้อมูลเดโมย้อนหลัง 400 วัน) — เปิดดูแล้วต้องบอกเหตุผล ไม่ใช่รูปแตก
    today = date.today()
    phone.select_option("#period", "custom")
    phone.fill("#from", (today - timedelta(days=410)).isoformat())
    phone.fill("#to", (today - timedelta(days=390)).isoformat())
    phone.click("#filters button[type=submit]")
    # รอให้ผลของช่วงใหม่มาแทนตารางเดิมก่อน ไม่งั้นจะไปคลิกแถวของ "วันนี้" ที่ยังค้างอยู่
    expect(phone.locator("#result-title")).to_contain_text("ถึง")
    row = phone.locator("tr.person").first
    expect(row).to_be_visible()
    row.get_by_role("button", name="ดูรูป").click()
    expect(phone.locator("tr.detail:not([hidden]) .missing").first).to_contain_text("ไม่พบรูป")


# ---------- ใช้งานได้ทุกขนาดจอ + คีย์บอร์ด ----------

@pytest.mark.parametrize("size", [NARROW, PHONE, DESKTOP], ids=["320", "375", "1280"])
@pytest.mark.parametrize("path", ["/login", "/register"])
def test_auth_pages_fit_viewport(page: Page, size, path):
    page.set_viewport_size(size)
    page.goto(path)
    expect(page.locator("#submit")).to_be_visible()
    assert no_horizontal_scroll(page)
    btn = page.locator("#submit").bounding_box()
    assert btn["height"] >= 44 and btn["x"] >= 0 and btn["x"] + btn["width"] <= size["width"]


@pytest.mark.parametrize("size", [NARROW, PHONE, DESKTOP], ids=["320", "375", "1280"])
def test_app_pages_fit_viewport(page: Page, size):
    page.set_viewport_size(size)
    login_as(page, 2)
    assert no_horizontal_scroll(page)
    page.goto("/boss")
    expect(page.locator("tr.person").first).to_be_visible()
    assert no_horizontal_scroll(page), "แดชบอร์ดเลื่อนข้างที่ความกว้าง " + str(size["width"])
    shot(page, f"dashboard-{size['width']}")


def test_keyboard_can_complete_login_with_visible_focus(page: Page):
    page.set_viewport_size(PHONE)
    page.goto("/login")
    stops = []
    for _ in range(4):
        page.keyboard.press("Tab")
        stops.append(page.evaluate(
            "(() => { const e = document.activeElement; const s = getComputedStyle(e);"
            " return [e.id || e.tagName, s.outlineStyle, parseFloat(s.outlineWidth)]; })()"))
    ids = [s[0] for s in stops]
    assert ids[:3] == ["employee", "pin", "submit"], ids
    for ident, style, width in stops:
        assert style != "none" and width >= 2, f"{ident} ไม่มีวงโฟกัสที่มองเห็น"
    page.select_option("#employee", "2")
    page.focus("#pin")
    page.keyboard.type(DEMO_PIN)
    page.keyboard.press("Enter")  # ส่งฟอร์มด้วยปุ่ม Enter ในช่อง PIN ไม่ต้องใช้เมาส์
    expect(page.locator("#employee-name")).to_have_text("สมหญิง รักงาน")


def test_pin_input_uses_numeric_keyboard_and_password_manager_hints(page: Page):
    page.goto("/login")
    pin = page.locator("#pin")
    expect(pin).to_have_attribute("inputmode", "numeric")
    expect(pin).to_have_attribute("autocomplete", "current-password")
    expect(pin).to_have_attribute("type", "password")
    expect(pin).to_have_attribute("maxlength", "6")
    assert page.locator("label[for=pin]").count() == 1 and page.locator("label[for=employee]").count() == 1
    page.goto("/register")
    expect(page.locator("#pin")).to_have_attribute("autocomplete", "new-password")
    expect(page.locator("#name")).to_have_attribute("autocomplete", "name")
    font_px = page.evaluate("parseFloat(getComputedStyle(document.querySelector('#pin')).fontSize)")
    assert font_px >= 16  # น้อยกว่านี้ iOS จะซูมหน้าเองตอนแตะช่อง
