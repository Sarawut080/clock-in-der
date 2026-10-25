// หน้าลงทะเบียน — ชื่อ-นามสกุล + ตั้ง PIN 6 หลัก แล้วเข้าสู่ระบบทันที
// ต้องโหลด common.js ก่อน
const NETWORK_ERROR = "เชื่อมต่อระบบไม่ได้ ตรวจสอบว่าต่อ Wi-Fi ของออฟฟิศอยู่ แล้วลองอีกครั้ง";

class RegisterPage extends AuthFormPage {
  constructor(api, notice) {
    super(api, notice, $("form"), $("submit"));
    this.name = $("name");
    this.pin = $("pin");
    this.confirm = $("pin-confirm");
    this.inputs = [this.name, this.pin, this.confirm];
    this.codeFields = {
      INVALID_NAME: this.name,
      NAME_TAKEN: this.name,
      INVALID_PIN: this.pin,
      PIN_MISMATCH: this.confirm,
    };
  }

  validate() {
    const problems = [];
    if (!this.name.value.trim()) problems.push([this.name, "ใส่ชื่อ-นามสกุลของคุณ"]);
    if (!PIN_PATTERN.test(this.pin.value.trim())) {
      problems.push([this.pin, "ใส่ PIN เป็นตัวเลข 6 หลัก"]);
    } else if (this.confirm.value.trim() !== this.pin.value.trim()) {
      problems.push([this.confirm, "PIN 2 ช่องไม่ตรงกัน ใส่อีกครั้ง"]);
    }
    return problems;
  }

  async submit() {
    await this.api.postJson("/api/auth/register", {
      name: this.name.value.trim(),
      pin: this.pin.value.trim(),
      pin_confirm: this.confirm.value.trim(),
    });
    location.replace("/");
  }
}

new RegisterPage(new ApiClient(NETWORK_ERROR), new Notice());
