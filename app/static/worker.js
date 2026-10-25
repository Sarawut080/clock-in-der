// หน้าพนักงาน (UC1–UC4) เดินตาม flowchart ส่วนที่ 1
const FULL_DAY_MINUTES = 480;
const NETWORK_ERROR = "เชื่อมต่อระบบไม่ได้ ตรวจสอบว่าต่อ Wi-Fi ของออฟฟิศอยู่ แล้วลองอีกครั้ง";
const LABEL = { in: "เข้างาน", out: "ออกงาน" };

const $ = (id) => document.getElementById(id);
const state = { employeeId: null, nextType: null, photo: null, previewUrl: null };

$("today-label").textContent = new Date().toLocaleDateString("th-TH", {
  weekday: "long", day: "numeric", month: "long", year: "numeric",
});

// ---------- ตัวช่วย ----------

async function api(path, options) {
  let res;
  let body;
  try {
    res = await fetch(path, options);
    body = await res.json();
  } catch {
    throw new Error(NETWORK_ERROR);
  }
  if (!res.ok || body.ok === false) throw new Error(body.message || NETWORK_ERROR);
  return body;
}

function showError(message) {
  $("notice").textContent = message;
  $("notice").hidden = false;
}
function clearError() { $("notice").hidden = true; }

// เซิร์ฟเวอร์ส่ง ISO ที่มี +07:00 เสมอ (contract) จึงตัด HH:MM ได้ตรงๆ ไม่ต้องแปลงเขตเวลา
const hhmm = (iso) => iso.slice(11, 16);

function hoursText(minutes) {
  return `${Math.floor(minutes / 60)} ชม. ${minutes % 60} นาที`;
}

// ---------- UC1: รายชื่อ ----------

async function loadEmployees() {
  try {
    for (const e of await api("/api/employees")) {
      const opt = document.createElement("option");
      opt.value = e.id;
      opt.textContent = e.name;
      $("employee").appendChild(opt);
    }
  } catch (err) {
    showError(err.message);
  }
}

// ---------- UC4: ชั่วโมงสะสมวันนี้ ----------

function renderHours(data) {
  const hours = $("hours");
  const note = $("hours-note");
  hours.classList.toggle("is-text", !data.is_complete);

  if (!data.is_complete) {
    // alternative flow ของ UC4: มีรอบที่ยังไม่ออกงาน → ไม่แสดงตัวเลข
    const openIn = data.events.filter((e) => e.type === "in").at(-1);
    hours.textContent = "ข้อมูลยังไม่ครบ";
    note.textContent = `เข้างานเมื่อ ${hhmm(openIn.recorded_at)} น. ชั่วโมงของรอบนี้จะนับเมื่อบันทึกออกงาน`;
  } else {
    const m = data.worked_minutes;
    hours.innerHTML = `${Math.floor(m / 60)}<small>ชม.</small>${m % 60}<small>นาที</small>`;
    note.textContent = m >= FULL_DAY_MINUTES
      ? "ครบ 8 ชั่วโมงแล้ว"
      : `ขาดอีก ${hoursText(FULL_DAY_MINUTES - m)} จึงจะครบ 8 ชั่วโมง`;
  }

  const done = data.is_complete ? data.worked_minutes : 0;
  const cells = [];
  for (let i = 0; i < 8; i++) {
    const fill = Math.max(0, Math.min(1, (done - i * 60) / 60));
    cells.push(`<span class="punch-cell"><i style="width:${fill * 100}%"></i></span>`);
  }
  const punch = $("punch");
  punch.innerHTML = cells.join("");
  punch.classList.toggle("is-full", done >= FULL_DAY_MINUTES);
  punch.setAttribute("aria-label", data.is_complete
    ? `ทำงานแล้ว ${hoursText(done)} จากเกณฑ์ 8 ชั่วโมง`
    : "ข้อมูลยังไม่ครบ");
}

function renderStamps(events) {
  const list = $("stamps");
  list.replaceChildren();
  if (events.length === 0) {
    const li = document.createElement("li");
    li.className = "empty";
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

async function loadToday() {
  const data = await api("/api/me/today?employee_id=" + state.employeeId);
  renderHours(data);
  renderStamps(data.events);

  // ปุ่มเดียว ระบบเลือกประเภทให้จากสถานะล่าสุด (จุดตัดสินใจใน flowchart)
  state.nextType = data.last_type === "in" ? "out" : "in";
  $("clock-btn").textContent = "บันทึก" + LABEL[state.nextType];

  $("status").hidden = false;
  $("action").hidden = false;
  showStep("start");
}

// ---------- UC2 / UC3: ถ่ายรูปและบันทึก ----------

function clearPhoto() {
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  state.photo = null;
  state.previewUrl = null;
  $("photo").value = "";
  $("preview").hidden = true;
  $("preview").removeAttribute("src");
  $("camera-label").textContent = "ถ่ายรูป";
  $("confirm-btn").disabled = true;
}

function showStep(step) {
  $("clock-btn").hidden = step !== "start";
  $("photo-step").hidden = step !== "photo";
  $("done").hidden = step !== "done";
  if (step !== "photo") clearPhoto();
}

$("employee").addEventListener("change", async (e) => {
  clearError();
  state.employeeId = e.target.value || null;
  $("status").hidden = true;
  $("action").hidden = true;
  if (!state.employeeId) return;
  try {
    await loadToday();
  } catch (err) {
    showError(err.message);
  }
});

$("clock-btn").addEventListener("click", () => {
  clearError();
  const label = LABEL[state.nextType];
  $("photo-hint").textContent = `ถ่ายรูปตนเองเพื่อยืนยันการ${label}`;
  $("confirm-btn").textContent = "บันทึก" + label;
  showStep("photo");
  $("camera-label").focus();
});

// BR1: ต้องมีรูปก่อนจึงกดบันทึกได้
$("photo").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  state.photo = file;
  state.previewUrl = URL.createObjectURL(file);
  $("preview").src = state.previewUrl;
  $("preview").hidden = false;
  $("camera-label").textContent = "ถ่ายใหม่";
  $("confirm-btn").disabled = false;
});

// ยกเลิก — ไม่บันทึกข้อมูล (ตาม flowchart)
$("cancel-btn").addEventListener("click", () => showStep("start"));

$("confirm-btn").addEventListener("click", async () => {
  if (!state.photo) return;
  const form = new FormData();
  form.append("employee_id", state.employeeId);
  form.append("type", state.nextType);
  form.append("photo", state.photo);

  $("confirm-btn").disabled = true;  // กันกดซ้ำระหว่างรออัปโหลด
  try {
    const result = await api("/api/clock", { method: "POST", body: form });
    $("done-label").textContent = `บันทึก${LABEL[result.type]}แล้ว`;
    $("done-time").textContent = hhmm(result.recorded_at) + " น.";
    showStep("done");
    $("done-btn").focus();
  } catch (err) {
    showError(err.message);
    $("confirm-btn").disabled = false;
  }
});

$("done-btn").addEventListener("click", async () => {
  try {
    await loadToday();
  } catch (err) {
    showError(err.message);
  }
});

loadEmployees();
