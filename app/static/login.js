// หน้าเข้าสู่ระบบ — เลือกชื่อ + PIN 6 หลัก
// ต้องโหลด common.js ก่อน
const NETWORK_ERROR = "เชื่อมต่อระบบไม่ได้ ตรวจสอบว่าต่อ Wi-Fi ของออฟฟิศอยู่ แล้วลองอีกครั้ง";

class LoginPage extends AuthFormPage {
  constructor(api, notice) {
    super(api, notice, $("form"), $("submit"));
    this.employee = $("employee");
    this.pin = $("pin");
    this.inputs = [this.employee, this.pin];
    this.codeFields = {
      EMPLOYEE_NOT_FOUND: this.employee,
      INVALID_PIN: this.pin,
      WRONG_PIN: this.pin,
      LOCKED: this.pin,
    };
  }

  async init() {
    try {
      for (const e of await this.api.request("/api/employees")) {
        const opt = document.createElement("option");
        opt.value = e.id;
        opt.textContent = e.name;
        this.employee.appendChild(opt);
      }
    } catch (err) {
      this.notice.show(err.message);
    }
  }

  validate() {
    const problems = [];
    if (!this.employee.value) problems.push([this.employee, "เลือกชื่อของคุณ"]);
    if (!PIN_PATTERN.test(this.pin.value.trim())) problems.push([this.pin, "ใส่ PIN เป็นตัวเลข 6 หลัก"]);
    return problems;
  }

  async submit() {
    await this.api.postJson("/api/auth/login", {
      employee_id: Number(this.employee.value),
      pin: this.pin.value.trim(),
    });
    location.replace("/");
  }
}

new LoginPage(new ApiClient(NETWORK_ERROR), new Notice()).init();
