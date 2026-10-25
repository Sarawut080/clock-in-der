// ส่วนที่ใช้ร่วมกันทุกหน้า
const $ = (id) => document.getElementById(id);

class ApiClient {
  constructor(networkError) {
    this.networkError = networkError;
  }

  async request(path, options) {
    let res;
    let body;
    try {
      res = await fetch(path, options);
      body = await res.json();
    } catch {
      throw new Error(this.networkError);
    }
    if (body.error === "UNAUTHENTICATED" && !ApiClient.onAuthPage()) {
      location.assign("/login");  // session หมดอายุหรือยังไม่เข้าสู่ระบบ
    }
    if (!res.ok || body.ok === false) {
      const err = new Error(body.message || this.networkError);
      err.code = body.error;
      throw err;
    }
    return body;
  }

  postJson(path, data) {
    return this.request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  }

  static onAuthPage() {
    return location.pathname === "/login" || location.pathname === "/register";
  }
}

class Notice {
  constructor(id = "notice") {
    this.id = id;
  }

  show(message) {
    $(this.id).textContent = message;
  }

  clear() {
    $(this.id).textContent = "";
  }
}

// ข้อผิดพลาดใต้ช่องที่ผิด: aria-invalid + aria-describedby ให้ screen reader อ่านพร้อมช่อง
// ไอคอนเป็น Lucide circle-alert (ISC) เพื่อไม่ให้สื่อด้วยสีอย่างเดียว
class FieldError {
  static ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>';

  constructor(input) {
    this.input = input;
    this.box = $(input.id + "-error");
  }

  show(message) {
    this.box.replaceChildren();
    this.box.insertAdjacentHTML("afterbegin", FieldError.ICON);
    const text = document.createElement("span");
    text.textContent = message;
    this.box.appendChild(text);
    this.input.setAttribute("aria-invalid", "true");
  }

  clear() {
    this.box.replaceChildren();
    this.input.removeAttribute("aria-invalid");
  }
}

const PIN_PATTERN = /^[0-9]{6}$/;

// ปุ่มส่งฟอร์ม: ระหว่างรอคงข้อความเดิม ใช้ aria-disabled (ไม่ใช้ disabled เพราะทำให้โฟกัสหลุด) แล้วกันกดซ้ำเอง
class PendingButton {
  constructor(button) {
    this.button = button;
  }

  get busy() {
    return this.button.getAttribute("aria-disabled") === "true";
  }

  start() {
    this.button.setAttribute("aria-disabled", "true");
  }

  stop() {
    this.button.removeAttribute("aria-disabled");
  }
}

// โครงฟอร์มเข้าสู่ระบบ/ลงทะเบียน: ตรวจตอนกดส่ง (ไม่ปิดปุ่มรอกรอกครบ) → ข้อผิดพลาดใต้ช่อง + โฟกัสช่องแรกที่ผิด
// ข้อผิดพลาดจากเซิร์ฟเวอร์ที่ผูกกับช่องใดช่องหนึ่ง (codeFields) แสดงใต้ช่องนั้น ที่เหลือขึ้นแถบ #notice
class AuthFormPage {
  constructor(api, notice, form, submitButton) {
    this.api = api;
    this.notice = notice;
    this.pending = new PendingButton(submitButton);
    this.inputs = [];
    this.codeFields = {};
    form.addEventListener("submit", (e) => this.onSubmit(e));
  }

  // คืนรายการ [input, ข้อความ] ของช่องที่ไม่ผ่าน เรียงตามลำดับในหน้า
  validate() {
    return [];
  }

  async submit() {}

  async onSubmit(e) {
    e.preventDefault();
    if (this.pending.busy) return;
    this.notice.clear();
    this.inputs.forEach((input) => new FieldError(input).clear());
    const problems = this.validate();
    if (problems.length > 0) {
      problems.forEach(([input, message]) => new FieldError(input).show(message));
      problems[0][0].focus();
      return;
    }
    this.pending.start();
    try {
      await this.submit();
    } catch (err) {
      this.handleError(err);
    } finally {
      this.pending.stop();
    }
  }

  handleError(err) {
    const input = this.codeFields[err.code];
    if (!input) {
      this.notice.show(err.message);
      return;
    }
    new FieldError(input).show(err.message);
    input.focus();
    if (err.code === "WRONG_PIN") input.select();
  }
}
