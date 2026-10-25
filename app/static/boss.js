// หน้าเจ้านาย (UC5–UC7) เดินตาม flowchart ส่วนที่ 2
const NETWORK_ERROR = "เชื่อมต่อระบบไม่ได้ ตรวจสอบว่าเครื่องนี้ต่อเครือข่ายของออฟฟิศอยู่ แล้วลองอีกครั้ง";
const PHOTO_RETENTION_DAYS = 365;  // D8

// ใช้คำตามคำอภิธานศัพท์ใน 01-SA (สถานะการทำงาน)
const STATUS = {
  OK:         { cls: "badge-ok",         icon: "✓", text: "ครบ 8 ชม." },
  SHORT:      { cls: "badge-short",      icon: "✕", text: "ไม่ครบ 8 ชม." },
  INCOMPLETE: { cls: "badge-incomplete", icon: "!", text: "ข้อมูลยังไม่ครบ" },
};

const $ = (id) => document.getElementById(id);
let latestRequest = 0;

// สร้าง element ด้วย textContent เสมอ ไม่ต่อสตริง HTML จากข้อมูลในระบบ
function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  node.append(...children);
  return node;
}

async function api(path) {
  let res;
  let body;
  try {
    res = await fetch(path);
    body = await res.json();
  } catch {
    throw new Error(NETWORK_ERROR);
  }
  if (!res.ok || body.ok === false) throw new Error(body.message || NETWORK_ERROR);
  return body;
}

function localISODate(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

const thaiDate = (iso, opts = { day: "numeric", month: "short", year: "numeric" }) =>
  new Date(iso + "T00:00:00").toLocaleDateString("th-TH", opts);

const hoursText = (m) => `${Math.floor(m / 60)} ชม. ${String(m % 60).padStart(2, "0")} นาที`;

function showError(message) {
  $("notice").textContent = message;
  $("notice").hidden = false;
}

// ---------- หัวผลลัพธ์ ----------

function renderHead(rows, filter) {
  const today = localISODate(new Date());
  let title = filter.from === filter.to
    ? (filter.from === today ? "วันนี้ " : "") + thaiDate(filter.from, { weekday: "long", day: "numeric", month: "long", year: "numeric" })
    : `${thaiDate(filter.from)} ถึง ${thaiDate(filter.to)}`;
  if (filter.employeeName) title += ` ของ${filter.employeeName}`;
  $("result-title").textContent = title;

  const counts = { OK: 0, SHORT: 0, INCOMPLETE: 0 };
  for (const r of rows) counts[r.status]++;
  $("counts").replaceChildren(
    ...Object.entries(STATUS).map(([key, s]) =>
      el("span", { class: "badge " + s.cls }, `${s.text} ${counts[key]}`)),
  );
}

// ---------- ตาราง ----------

function badge(status) {
  const s = STATUS[status];
  return el("span", { class: "badge " + s.cls }, el("span", { "aria-hidden": "true", text: s.icon }), s.text);
}

// UC7: รูปประกอบของแต่ละรายการ
function photoFigure(ev, name) {
  const label = ev.type === "in" ? "เข้างาน" : "ออกงาน";
  const time = ev.recorded_at.slice(11, 16) + " น.";
  const img = el("img", { src: "/photos/" + encodeURIComponent(ev.photo_path), alt: `${name} ${label} ${time}`, loading: "lazy" });
  img.addEventListener("error", () => {
    const ageDays = (Date.now() - new Date(ev.recorded_at)) / 86400000;
    const why = ageDays > PHOTO_RETENTION_DAYS ? "รูปที่เก่ากว่า 1 ปีจะถูกลบตามนโยบาย" : "ไฟล์รูปหายไปจากเครื่องเซิร์ฟเวอร์";
    img.replaceWith(el("div", { class: "missing" }, el("span", {}, el("strong", { text: "ไม่พบรูป" }), el("br"), why)));
  });
  return el("figure", { class: "shot" }, img, el("figcaption", {}, `${label} `, el("strong", { class: "num", text: time })));
}

let rowSeq = 0;
function personRows(r, colCount) {
  const detailId = "detail-" + rowSeq++;
  const btn = el("button", { class: "name-btn", type: "button", "aria-expanded": "false", "aria-controls": detailId, text: r.name });
  const tr = el("tr", {},
    el("td", {}, btn),
    el("td", { class: "num", text: r.first_in ? r.first_in + " น." : "-" }),
    r.last_out
      ? el("td", { class: "num", text: r.last_out + " น." })
      : el("td", { class: "muted", text: "ยังไม่ออกงาน" }),
    el("td", { class: "num", text: r.status === "INCOMPLETE" ? "-" : hoursText(r.worked_minutes) }),
    el("td", {}, badge(r.status)),
  );
  const detail = el("tr", { class: "detail", id: detailId, hidden: "" },
    el("td", { colspan: colCount }, el("div", { class: "photos" }, ...r.events.map((ev) => photoFigure(ev, r.name)))));
  btn.addEventListener("click", () => {
    const open = detail.hidden;
    detail.hidden = !open;
    btn.setAttribute("aria-expanded", String(open));
  });
  return [tr, detail];
}

function renderTable(rows, grouped) {
  if (rows.length === 0) {
    $("table-wrap").replaceChildren(el("div", { class: "empty" },
      el("strong", { text: "ไม่มีการบันทึกเวลาในช่วงที่เลือก" }),
      el("span", { class: "muted", text: "ลองขยายช่วงวันที่ หรือเปลี่ยนพนักงานเป็น “ทุกคน”" })));
    return;
  }

  const cols = ["ชื่อ", "เข้างานครั้งแรก", "ออกงานครั้งสุดท้าย", "ชั่วโมงทำงานสะสม", "สถานะ"];
  const table = el("table", {},
    el("caption", { class: "visually-hidden", text: "สรุปเวลาเข้า-ออกงาน กดชื่อเพื่อดูรูปประกอบ" }),
    el("thead", {}, el("tr", {}, ...cols.map((c) => el("th", { scope: "col", text: c })))));

  if (!grouped) {
    table.appendChild(el("tbody", {}, ...rows.flatMap((r) => personRows(r, cols.length))));
  } else {
    // ช่วงวันที่: แยกกลุ่มตามวัน วันล่าสุดอยู่บน
    const byDate = new Map();
    for (const r of rows) {
      if (!byDate.has(r.date)) byDate.set(r.date, []);
      byDate.get(r.date).push(r);
    }
    for (const date of [...byDate.keys()].sort().reverse()) {
      const head = el("tr", { class: "group" }, el("th", { scope: "rowgroup", colspan: cols.length,
        text: thaiDate(date, { weekday: "long", day: "numeric", month: "long", year: "numeric" }) }));
      table.appendChild(el("tbody", {}, head, ...byDate.get(date).flatMap((r) => personRows(r, cols.length))));
    }
  }
  $("table-wrap").replaceChildren(table);
}

// ---------- โหลดข้อมูล ----------

async function load() {
  $("notice").hidden = true;
  const select = $("employee");
  const filter = {
    from: $("from").value,
    to: $("to").value,
    employeeId: select.value,
    employeeName: select.value ? select.selectedOptions[0].textContent : "",
  };
  const requestId = ++latestRequest;
  try {
    let rows;
    let grouped;
    if (filter.from === filter.to && !filter.employeeId) {
      rows = await api("/api/report/daily?date=" + filter.from);  // FR5
      grouped = false;
    } else {
      const q = new URLSearchParams({ from: filter.from, to: filter.to });  // FR6
      if (filter.employeeId) q.set("employee_id", filter.employeeId);
      rows = await api("/api/report/range?" + q);
      grouped = filter.from !== filter.to;
    }
    if (requestId !== latestRequest) return;  // มีการกรองใหม่ระหว่างรอ ทิ้งผลเก่า
    renderHead(rows, filter);
    renderTable(rows, grouped);
  } catch (err) {
    if (requestId === latestRequest) showError(err.message);
  }
}

$("filters").addEventListener("submit", (e) => {
  e.preventDefault();
  load();
});

(async () => {
  const today = localISODate(new Date());
  $("from").value = today;  // UC5: ค่าเริ่มต้นคือวันนี้
  $("to").value = today;
  try {
    for (const e of await api("/api/employees")) $("employee").appendChild(el("option", { value: e.id, text: e.name }));
  } catch (err) {
    showError(err.message);
  }
  load();
})();
