// หน้าพนักงาน (UC1–UC4) เดินตาม flowchart ส่วนที่ 1
// ต้องโหลด common.js ก่อน
const FULL_DAY_MINUTES = 480;
const NETWORK_ERROR = "เชื่อมต่อระบบไม่ได้ ตรวจสอบว่าต่อ Wi-Fi ของออฟฟิศอยู่ แล้วลองอีกครั้ง";
const LABEL = { in: "เข้างาน", out: "ออกงาน" };

// เซิร์ฟเวอร์ส่ง ISO ที่มี +07:00 เสมอ (contract) จึงตัด HH:MM ได้ตรงๆ ไม่ต้องแปลงเขตเวลา
const hhmm = (iso) => iso.slice(11, 16);
const hoursText = (m) => `${Math.floor(m / 60)} ชม. ${m % 60} นาที`;

const STALE_RUNNING_MINUTES = 720;  // เข้างานค้างเกิน 12 ชม. = น่าจะลืมกดออกงาน
const TICK_MS = 10_000;             // นับสดทุก 10 วินาที (ตัวเลขเปลี่ยนทุกนาที แต่เช็คถี่กว่านั้นให้เปลี่ยนตรงเวลา)
const THAI_OFFSET_MS = 7 * 3600 * 1000;

// ชั่วโมงสดของวันนี้ = ที่ออกงานแล้ว + รอบที่ยังไม่ออกนับถึงตอนนี้ (แสดงหน้าพนักงานเท่านั้น ไม่ใช่ชั่วโมงทางการ)
// ไม่เชื่อนาฬิกามือถือ (BR2): เก็บส่วนต่างระหว่าง server_now กับ Date.now() ตอนโหลด แล้วนับต่อจากนั้น
// ใช้ Date.now() ไม่ใช่ตัวนับของ timer เพราะเครื่องหลับ/พักหน้าจอแล้ว timer ถูกหยุด แต่เวลาจริงเดินต่อ
class LiveHours {
  constructor(data) {
    this.completed = data.worked_minutes;
    this.openSince = data.open_since ? Date.parse(data.open_since) : null;
    this.offset = Date.parse(data.server_now) - Date.now();
    this.serverDay = data.server_now.slice(0, 10);  // วันที่เวลาไทย ตอนโหลด
  }

  get running() {
    return this.openSince !== null;
  }

  now() {
    return Date.now() + this.offset;
  }

  minutes() {
    if (!this.running) return this.completed;
    return this.completed + Math.max(0, Math.floor((this.now() - this.openSince) / 60000));
  }

  // ข้ามเที่ยงคืนเวลาไทยจากตอนโหลด: รอบที่ค้างไม่ถูกยกไปวันใหม่ (BR3 นับเฉพาะวันนี้) ต้องถามเซิร์ฟเวอร์ใหม่
  dayChanged() {
    return new Date(this.now() + THAI_OFFSET_MS).toISOString().slice(0, 10) !== this.serverDay;
  }
}

class WorkerPage {
  constructor(api, notice) {
    this.api = api;
    this.notice = notice;
    this.employeeId = null;
    this.nextType = null;
    this.photo = null;
    this.previewUrl = null;
    this.live = null;
    this.openSinceText = null;
    this.timer = null;
    this.lastPainted = null;
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
    // มือถือพักหน้าจอ/สลับแอปแล้ว timer หยุด — กลับมาเห็นหน้าเมื่อไหร่ถามเซิร์ฟเวอร์ใหม่ (ไม่ poll เป็นระยะ)
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden && this.employeeId) this.refreshStatus().catch(() => {});
    });
  }

  // ---------- UC4: ชั่วโมงสะสมวันนี้ ----------

  renderHours(data) {
    this.live = new LiveHours(data);
    this.openSinceText = data.open_since ? hhmm(data.open_since) : null;
    this.lastPainted = null;
    this.paint();
    this.startTicking();
  }

  // วาดตัวเลข ข้อความ และแถบจากเวลา "ตอนนี้" — เรียกซ้ำได้ ไม่วาดใหม่ถ้านาทียังเท่าเดิม
  paint() {
    const live = this.live;
    const m = live.minutes();
    const key = `${m}|${live.running}`;
    if (key === this.lastPainted) return;
    this.lastPainted = key;

    const running = live.running;
    $("live-badge").hidden = !running;
    $("hours").innerHTML = `${Math.floor(m / 60)}<small>ชม.</small>${m % 60}<small>นาที</small>`;

    const note = $("hours-note");
    note.classList.toggle("is-warn", running && m >= STALE_RUNNING_MINUTES);
    if (!running) {
      note.textContent = m >= FULL_DAY_MINUTES
        ? "ครบ 8 ชั่วโมงแล้ว"
        : `ขาดอีก ${hoursText(FULL_DAY_MINUTES - m)} จึงจะครบ 8 ชั่วโมง`;
    } else if (m >= STALE_RUNNING_MINUTES) {
      note.textContent = `เข้างานเมื่อ ${this.openSinceText} น. มานานผิดปกติ ลืมบันทึกออกงานหรือเปล่า`;
    } else if (m >= FULL_DAY_MINUTES) {
      note.textContent = "ครบ 8 ชั่วโมงแล้ว (ยังนับอยู่ จนกว่าจะบันทึกออกงาน)";
    } else {
      note.textContent = `เข้างานเมื่อ ${this.openSinceText} น. · ชั่วโมงนี้ยังไม่เป็นทางการ จะรวมเมื่อบันทึกออกงาน`;
    }

    // แถบ: เติมทีละชั่วโมงเต็มช่อง — ช่องที่ได้จากรอบที่ยังนับอยู่ (is-live) เป็นลายเฉียง ไม่ใช้สีอย่างเดียวแยก
    const filled = Math.min(8, Math.floor(m / 60));
    const solid = Math.min(filled, Math.floor(live.completed / 60));
    const cells = [];
    for (let i = 0; i < 8; i++) {
      const cls = i >= filled ? "" : i < solid ? " is-filled" : " is-filled is-live";
      cells.push(`<span class="tape-cell${cls}"><i></i></span>`);
    }
    const tape = $("tape");
    tape.innerHTML = cells.join("");
    tape.classList.toggle("is-full", m >= FULL_DAY_MINUTES);
    // role="img" ไม่ใช่ live region: ป้ายชื่อเปลี่ยนตามเวลาได้โดยไม่ถูกอ่านออกเสียงทุกนาที
    tape.setAttribute("aria-label", `ทำงานแล้ว ${hoursText(m)}${running ? " (กำลังนับ)" : ""} จากเกณฑ์ 8 ชั่วโมง`);
    $("tape-legend").hidden = filled <= solid;
  }

  startTicking() {
    this.stopTicking();
    if (this.live && this.live.running) this.timer = setInterval(() => this.tick(), TICK_MS);
  }

  stopTicking() {
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
  }

  tick() {
    if (this.live.dayChanged()) {
      this.refreshStatus().catch(() => {});  // ข้ามเที่ยงคืน: รอบที่ค้างไม่ยกไปวันใหม่ ให้เซิร์ฟเวอร์ตัดสิน
      return;
    }
    this.paint();
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
