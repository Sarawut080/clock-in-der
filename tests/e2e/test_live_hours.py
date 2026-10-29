"""แถบ/ตัวเลขชั่วโมงหน้าพนักงานที่นับสดตอนกำลังทำงาน (รอบที่ยังไม่กดออกงาน)

กติกา: แถบเติมทีละชั่วโมงเต็มช่อง · ช่องที่ได้จากรอบที่ยังนับอยู่เป็นลายเฉียง (.is-live) ไม่ทางการ ·
ตัวเลขทางการ (แดชบอร์ด/สถานะ) ไม่เปลี่ยน — ดู tests/api/test_clock_api.py::TestLiveHours

เกณฑ์ชั่วโมง (2 ชม., 8 ชม., 12 ชม.) ทดสอบด้วยคำตอบจำลองของ /api/me/today ผ่าน page.route เพื่อไม่ผูกกับเวลาจริงของเครื่อง
(การเลื่อนนาฬิกาจริงข้ามเที่ยงคืนจะไปชนพฤติกรรม "ข้ามวันแล้วถามเซิร์ฟเวอร์ใหม่" ซึ่งทดสอบแยกต่างหาก)
"""
import re
from datetime import datetime, timedelta

import pytest
from playwright.sync_api import Page, expect

from app.mock_store import BKK
from tests.e2e.test_ui import NARROW, login_as, no_horizontal_scroll, phone, pick_photo, shot  # noqa: F401

pytestmark = pytest.mark.e2e

SERVER_NOW = datetime(2026, 10, 25, 14, 0, 0, tzinfo=BKK)


def iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def fake_today(*, completed: int = 0, running: int | None = None, now: datetime = SERVER_NOW) -> dict:
    """คำตอบ /api/me/today จำลอง: completed = นาทีที่ออกงานแล้ว, running = นาทีที่รอบเปิดอยู่นับถึง now"""
    open_since = None if running is None else iso(now - timedelta(minutes=running))
    return {
        "employee_id": 2, "name": "สมหญิง รักงาน",
        "last_type": "in" if open_since else None,
        "worked_minutes": completed, "is_complete": open_since is None,
        "live_minutes": completed + (running or 0),
        "open_since": open_since, "server_now": iso(now), "events": [],
    }


def serve_today(page: Page, *payloads: dict) -> list:
    """ตอบ /api/me/today ด้วยชุดคำตอบจำลองตามลำดับ (อันสุดท้ายซ้ำไปเรื่อยๆ) คืนรายการคำขอที่เข้ามา"""
    calls = []

    def handler(route):
        payload = payloads[min(len(calls), len(payloads) - 1)]
        calls.append(route.request.url)
        route.fulfill(json=payload)

    page.route("**/api/me/today*", handler)
    return calls


def open_worker_page(page: Page, *payloads: dict) -> list:
    calls = serve_today(page, *payloads)
    login_as(page, 2)
    expect(page.locator("#hours")).to_be_visible()
    return calls


def cells(page: Page, selector: str) -> int:
    return page.locator(f".tape-cell{selector}").count()


# ---------- เกณฑ์ของแถบ: ทีละชั่วโมงเต็มช่อง ----------

def test_two_hours_running_fills_two_striped_cells(phone: Page):
    open_worker_page(phone, fake_today(running=125))
    expect(phone.locator("#hours")).to_have_text("2ชม.5นาที")
    expect(phone.locator("#live-badge")).to_be_visible()
    assert cells(phone, ".is-filled") == 2 and cells(phone, ".is-live") == 2 and cells(phone, ".is-filled:not(.is-live)") == 0
    expect(phone.locator("#tape-legend")).to_be_visible()
    expect(phone.locator("#hours-note")).to_contain_text("เข้างานเมื่อ 11:55 น.")
    expect(phone.locator("#hours-note")).to_contain_text("ยังไม่เป็นทางการ")
    label = phone.locator("#tape").get_attribute("aria-label")
    assert "2 ชม. 5 นาที" in label and "กำลังนับ" in label
    shot(phone, "worker-live-2h")


@pytest.mark.parametrize(
    "minutes,filled",
    [(0, 0), (59, 0), (60, 1), (119, 1), (120, 2), (299, 4), (479, 7)],
)
def test_cells_fill_only_when_a_whole_hour_is_complete(phone: Page, minutes, filled):
    open_worker_page(phone, fake_today(running=minutes))
    assert cells(phone, ".is-filled") == filled
    assert cells(phone, "") == 8  # โครงแถบ 8 ช่องเสมอ
    assert "is-full" not in (phone.locator("#tape").get_attribute("class") or "")


def test_closed_hours_are_solid_and_running_hours_are_striped(phone: Page):
    open_worker_page(phone, fake_today(completed=90, running=70))  # ปิดแล้ว 1:30 + กำลังนับ 1:10 = 2:40
    expect(phone.locator("#hours")).to_have_text("2ชม.40นาที")
    assert cells(phone, ".is-filled") == 2
    assert cells(phone, ".is-filled:not(.is-live)") == 1  # 1 ชม. ที่บันทึกครบแล้ว = ทึบ
    assert cells(phone, ".is-live") == 1                  # อีก 1 ช่องได้มาจากรอบที่ยังนับอยู่


def test_finished_day_has_no_live_marks_and_shows_the_remaining_time(phone: Page):
    open_worker_page(phone, fake_today(completed=180))
    expect(phone.locator("#hours")).to_have_text("3ชม.0นาที")
    expect(phone.locator("#live-badge")).to_be_hidden()
    expect(phone.locator("#tape-legend")).to_be_hidden()
    assert cells(phone, ".is-filled") == 3 and cells(phone, ".is-live") == 0
    expect(phone.locator("#hours-note")).to_have_text("ขาดอีก 5 ชม. 0 นาที จึงจะครบ 8 ชั่วโมง")


def test_eight_hours_while_running_turns_green_and_says_still_counting(phone: Page):
    open_worker_page(phone, fake_today(running=485))
    assert cells(phone, ".is-filled") == 8
    assert "is-full" in phone.locator("#tape").get_attribute("class")
    expect(phone.locator("#hours-note")).to_contain_text("ครบ 8 ชั่วโมงแล้ว (ยังนับอยู่")


def test_twelve_hours_still_running_warns_about_forgotten_clock_out(phone: Page):
    open_worker_page(phone, fake_today(running=13 * 60))
    note = phone.locator("#hours-note")
    expect(note).to_contain_text("ลืมบันทึกออกงานหรือเปล่า")
    expect(note).to_have_class(re.compile(r"is-warn"))
    assert cells(phone, ".is-filled") == 8  # แถบไม่เกิน 8 ช่อง แต่ตัวเลขนับต่อ
    expect(phone.locator("#hours")).to_have_text("13ชม.0นาที")


# ---------- การเดินของเวลา ----------

def test_numbers_tick_on_their_own_with_the_real_server(phone: Page):
    T = datetime.now()
    phone.clock.install(time=T)
    phone.clock.pause_at(T + timedelta(seconds=1))  # หยุดเวลาหน้าเว็บ แล้วเดินเองด้วย run_for เพื่อให้ผลแน่นอน
    login_as(phone, 4)
    phone.click("#clock-btn")
    pick_photo(phone)
    phone.click("#confirm-btn")
    expect(phone.locator("#done")).to_be_visible()
    phone.click("#done-btn")
    expect(phone.locator("#live-badge")).to_be_visible()
    expect(phone.locator("#hours")).to_have_text("0ชม.0นาที")

    phone.clock.run_for(65_000)   # timer เดินจริงทุก 10 วินาที → ครบ 1 นาที
    expect(phone.locator("#hours")).to_have_text("0ชม.1นาที")
    phone.clock.run_for(60 * 60 * 1000)   # อีก 1 ชม. → ช่องแรกขึ้นเป็นลายเฉียง
    expect(phone.locator("#hours")).to_have_text("1ชม.1นาที")
    assert cells(phone, ".is-live") == 1

    # ออกงาน: ป้ายกำลังนับและลายเฉียงหายทันที แล้วใช้ตัวเลขทางการจากเซิร์ฟเวอร์เท่านั้น
    # (ตรงนี้เลื่อนเฉพาะนาฬิกาฝั่งเบราว์เซอร์ เซิร์ฟเวอร์ยังเดินตามเวลาจริง จึงทางการ ≈ 0 นาที — ยืนยันว่าตัวเลขสดไม่รั่วเข้าตัวเลขทางการ)
    phone.click("#clock-btn")
    pick_photo(phone)
    phone.click("#confirm-btn")
    expect(phone.locator("#done")).to_be_visible()
    phone.click("#done-btn")
    expect(phone.locator("#live-badge")).to_be_hidden()
    assert cells(phone, ".is-live") == 0 and cells(phone, ".is-filled") == 0
    expect(phone.locator("#hours")).to_have_text("0ชม.0นาที")


def test_tab_coming_back_to_view_asks_the_server_again(phone: Page):
    calls = open_worker_page(phone, fake_today(running=30), fake_today(running=95))
    expect(phone.locator("#hours")).to_have_text("0ชม.30นาที")
    before = len(calls)
    # เหมือนเปิดหน้าจอมือถือกลับมา: timer ที่ถูกพักไม่เชื่อถือ ต้องถามเซิร์ฟเวอร์ใหม่
    phone.evaluate("() => { Object.defineProperty(document, 'hidden', { value: false, configurable: true }); document.dispatchEvent(new Event('visibilitychange')); }")
    expect(phone.locator("#hours")).to_have_text("1ชม.35นาที")
    assert len(calls) == before + 1


def test_crossing_midnight_drops_the_open_round_by_asking_the_server(phone: Page):
    # 23:59:30 ตามเซิร์ฟเวอร์ ยังนับอยู่ → ผ่านไป 1 นาทีข้ามเที่ยงคืน: รอบที่ค้างไม่ถูกยกไปวันใหม่ (BR3)
    near_midnight = datetime(2026, 10, 25, 23, 59, 30, tzinfo=BKK)
    new_day = datetime(2026, 10, 26, 0, 0, 40, tzinfo=BKK)
    phone.clock.install(time=datetime.now())
    calls = open_worker_page(phone, fake_today(running=600, now=near_midnight), fake_today(now=new_day))
    expect(phone.locator("#hours")).to_have_text("10ชม.0นาที")
    assert len(calls) == 1
    phone.clock.fast_forward(60_000)
    expect(phone.locator("#hours")).to_have_text("0ชม.0นาที")
    expect(phone.locator("#live-badge")).to_be_hidden()
    assert len(calls) == 2


# ---------- การเข้าถึงและขนาดจอ ----------

def test_live_updates_are_not_announced_every_minute(phone: Page):
    open_worker_page(phone, fake_today(running=125))
    assert phone.evaluate("() => !document.querySelector('#tape').closest('[aria-live]') && !document.querySelector('#hours').closest('[aria-live]')")
    expect(phone.locator("#announce")).to_have_text("")  # ช่องประกาศมีไว้ให้ตอนบันทึกสำเร็จเท่านั้น


def test_pulse_dot_respects_reduced_motion(phone: Page):
    open_worker_page(phone, fake_today(running=10))
    assert "live-pulse" in phone.evaluate("() => getComputedStyle(document.querySelector('.live-dot')).animationName")
    phone.emulate_media(reduced_motion="reduce")
    assert phone.evaluate("() => getComputedStyle(document.querySelector('.live-dot')).animationName") == "none"
    expect(phone.locator("#live-badge")).to_contain_text("กำลังนับ")  # ข้อความบอกสถานะอยู่เสมอ ไม่พึ่งการกะพริบ


@pytest.mark.parametrize("running", [125, 13 * 60], ids=["2h", "13h-warning"])
def test_worker_page_fits_a_320px_screen_while_counting(phone: Page, running):
    phone.set_viewport_size(NARROW)
    open_worker_page(phone, fake_today(running=running))
    assert no_horizontal_scroll(phone)
    box = phone.locator("#tape").bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= NARROW["width"]
