// หน้าพนักงาน (UC1–UC4) เดินตาม flowchart ส่วนที่ 1
// ต้องโหลด common.js ก่อน
const FULL_DAY_MINUTES = 480;
const NETWORK_ERROR = "เชื่อมต่อระบบไม่ได้ ตรวจสอบว่าต่อ Wi-Fi ของออฟฟิศอยู่ แล้วลองอีกครั้ง";
const LABEL = { in: "เข้างาน", out: "ออกงาน" };

// เซิร์ฟเวอร์ส่ง ISO ที่มี +07:00 เสมอ (contract) จึงตัด HH:MM ได้ตรงๆ ไม่ต้องแปลงเขตเวลา
const hhmm = (iso) => iso.slice(11, 16);
const hoursText = (m) => `${Math.floor(m / 60)} ชม. ${m % 60} นาที`;

class WorkerPage {
  constructor(api, notice) {
    this.api = api;
    this.notice = notice;
    this.employeeId = null;
    this.nextType = null;
    this.photo = null;
    this.previewUrl = null;
  }

  async init() {
    $("today-label").textContent = new Date().toLocaleDateString("th-TH", {
      weekday: "long", day: "numeric", month: "long", year: "numeric",
    });
    this.bindEvents();
    try {
      // ตัวตนมาจากการเข้าสู่ระบบ ไม่ต้องเลือกชื่อ (UC1) — ถ้ายังไม่เข้าสู่ระบบ ApiClient พาไป /login เอง
      const me = await this.api.request("/api/auth/me");
      this.employeeId = me.employee_id;
      $("employee-name").textContent = me.name;
      await this.loadToday();
    } catch (err) {
      this.notice.show(err.message);
    }
  }

  bindEvents() {
    $("logout-btn").addEventListener("click", () => this.onLogout());
    $("clock-btn").addEventListener("click", () => this.onClockClick());
    $("photo").addEventListener("change", (e) => this.onPhotoChange(e));
    $("cancel-btn").addEventListener("click", () => this.onCancel());
    $("confirm-btn").addEventListener("click", () => this.onConfirm());
    $("done-btn").addEventListener("click", () => this.onDone());
  }

  // ---------- UC4: ชั่วโมงสะสมวันนี้ ----------

  renderHours(data) {
    const hours = $("hours");
    hours.classList.toggle("is-text", !data.is_complete);

    if (!data.is_complete) {
      // alternative flow ของ UC4: มีรอบที่ยังไม่ออกงาน → ไม่แสดงตัวเลข
      const openIn = data.events.filter((e) => e.type === "in").at(-1);
      hours.textContent = "ข้อมูลยังไม่ครบ";
      $("hours-note").textContent = `เข้างานเมื่อ ${hhmm(openIn.recorded_at)} น. ชั่วโมงของรอบนี้จะนับเมื่อบันทึกออกงาน`;
    } else {
      const m = data.worked_minutes;
      hours.innerHTML = `${Math.floor(m / 60)}<small>ชม.</small>${m % 60}<small>นาที</small>`;
      $("hours-note").textContent = m >= FULL_DAY_MINUTES
        ? "ครบ 8 ชั่วโมงแล้ว"
        : `ขาดอีก ${hoursText(FULL_DAY_MINUTES - m)} จึงจะครบ 8 ชั่วโมง`;
    }

    const done = data.is_complete ? data.worked_minutes : 0;
    const cells = [];
    for (let i = 0; i < 8; i++) {
      const fill = Math.max(0, Math.min(1, (done - i * 60) / 60));
      cells.push(`<span class="tape-cell"><i style="width:${fill * 100}%"></i></span>`);
    }
    const tape = $("tape");
    tape.innerHTML = cells.join("");
    tape.classList.toggle("is-full", done >= FULL_DAY_MINUTES);
    tape.setAttribute("aria-label", data.is_complete
      ? `ทำงานแล้ว ${hoursText(done)} จากเกณฑ์ 8 ชั่วโมง`
      : "ข้อมูลยังไม่ครบ");
  }

  renderLog(events) {
    const list = $("log");
    list.replaceChildren();
    if (events.length === 0) {
      const li = document.createElement("li");
      li.className = "muted";
      li.textContent = "วันนี้ยังไม่มีการบันทึกเวลา";
      list.appendChild(li);
      return;
    }
    for (const ev of events) {
      const li = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = LABEL[ev.type];
      const time = document.createElement("span");
      time.className = "t";
      time.textContent = hhmm(ev.recorded_at) + " น.";
      li.append(label, time);
      list.appendChild(li);
    }
  }

  // โหลดและแสดงสถานะวันนี้ โดยไม่แตะขั้นตอนที่หน้าจออยู่
  async refreshStatus() {
    const data = await this.api.request("/api/me/today");
    this.renderHours(data);
    this.renderLog(data.events);

    // ปุ่มเดียว ระบบเลือกประเภทให้จากสถานะล่าสุด (จุดตัดสินใจใน flowchart)
    this.nextType = data.last_type === "in" ? "out" : "in";
    $("clock-btn").textContent = "บันทึก" + LABEL[this.nextType];
  }

  async loadToday() {
    await this.refreshStatus();
    $("action").hidden = false;
    this.showStep("start");
  }

  // ---------- UC2 / UC3: ถ่ายรูปและบันทึก ----------

  clearPhoto() {
    if (this.previewUrl) URL.revokeObjectURL(this.previewUrl);
    this.photo = null;
    this.previewUrl = null;
    $("photo").value = "";
    $("preview").hidden = true;
    $("preview").removeAttribute("src");
    $("camera-label").textContent = "ถ่ายรูป";
    $("confirm-btn").disabled = true;
  }

  showStep(step) {
    // ขั้นถ่ายรูปซ่อนสรุปชั่วโมงไว้ชั่วคราว ให้จอมือถือเห็นแค่สิ่งที่ต้องทำ
    $("status").hidden = !this.employeeId || step === "photo";
    $("clock-btn").hidden = step !== "start";
    $("photo-step").hidden = step !== "photo";
    $("done").hidden = step !== "done";
    if (step !== "photo") this.clearPhoto();
  }

  // ---------- ตัวจัดการเหตุการณ์ ----------

  async onLogout() {
    try {
      await this.api.request("/api/auth/logout", { method: "POST" });
    } catch (err) {
      this.notice.show(err.message);
      return;
    }
    location.replace("/login");
  }

  onClockClick() {
    this.notice.clear();
    const label = LABEL[this.nextType];
    $("photo-hint").textContent = `ถ่ายรูปตนเองเพื่อยืนยันการ${label}`;
    $("confirm-btn").textContent = "บันทึก" + label;
    this.showStep("photo");
    $("photo").focus();  // โฟกัสไปที่ช่องไฟล์ วงโฟกัสแสดงที่ปุ่ม "ถ่ายรูป" (ดู CSS)
  }

  // BR1: ต้องมีรูปก่อนจึงกดบันทึกได้
  onPhotoChange(e) {
    const file = e.target.files[0];
    if (!file) return;
    if (this.previewUrl) URL.revokeObjectURL(this.previewUrl);
    this.photo = file;
    this.previewUrl = URL.createObjectURL(file);
    $("preview").src = this.previewUrl;
    $("preview").hidden = false;
    $("camera-label").textContent = "ถ่ายใหม่";
    $("confirm-btn").disabled = false;
  }

  // ยกเลิก — ไม่บันทึกข้อมูล (ตาม flowchart)
  onCancel() {
    this.showStep("start");
    $("clock-btn").focus();
  }

  async onConfirm() {
    if (!this.photo) return;
    const form = new FormData();
    form.append("type", this.nextType);
    form.append("photo", this.photo);

    $("confirm-btn").disabled = true;  // กันกดซ้ำระหว่างรออัปโหลด
    try {
      const result = await this.api.request("/api/clock", { method: "POST", body: form });
      const message = `บันทึก${LABEL[result.type]}แล้ว`;
      const time = hhmm(result.recorded_at) + " น.";
      $("done-label").textContent = message;
      $("done-time").textContent = time;
      $("announce").textContent = `${message} เวลา ${time}`;
      // บันทึกสำเร็จแล้ว: อัปเดตสรุปด้านบนทันที ไม่ให้ขัดแย้งกับข้อความสำเร็จ
      // ถ้าโหลดสรุปไม่ได้ก็ไม่เป็นไร ผลบันทึกถูกยืนยันไปแล้วในแผงนี้
      await this.refreshStatus().catch(() => {});
      this.showStep("done");
      $("done-btn").focus();
    } catch (err) {
      this.notice.show(err.message);
      $("confirm-btn").disabled = false;
    }
  }

  onDone() {
    $("announce").textContent = "";
    this.showStep("start");
    $("clock-btn").focus();
  }
}

new WorkerPage(new ApiClient(NETWORK_ERROR), new Notice()).init();
