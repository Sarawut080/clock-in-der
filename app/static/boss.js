// หน้าเจ้านาย (UC5–UC7) เดินตาม flowchart ส่วนที่ 2
// ต้องโหลด common.js ก่อน
const NETWORK_ERROR = "เชื่อมต่อระบบไม่ได้ ตรวจสอบว่าเครื่องนี้ต่อเครือข่ายของออฟฟิศอยู่ แล้วลองอีกครั้ง";
const PHOTO_RETENTION_DAYS = 365;  // D8
const SVG_NS = "http://www.w3.org/2000/svg";

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

class DateText {
  static LONG = { weekday: "long", day: "numeric", month: "long", year: "numeric" };

  static localISODate(d) {
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  }

  static thai(iso, opts = { day: "numeric", month: "short", year: "numeric" }) {
    return new Date(iso + "T00:00:00").toLocaleDateString("th-TH", opts);
  }

  static hours(m) {
    return `${Math.floor(m / 60)} ชม. ${String(m % 60).padStart(2, "0")} นาที`;
  }
}

class StatusBadge {
  // ไอคอนจาก Lucide (ISC license, lucide.dev) circle-check / clock / circle-alert — viewBox 24 เส้น 2 ใช้ currentColor
  static ICONS = {
    OK: [["circle", { cx: 12, cy: 12, r: 10 }], ["path", { d: "m9 12 2 2 4-4" }]],
    SHORT: [["circle", { cx: 12, cy: 12, r: 10 }], ["polyline", { points: "12 6 12 12 16 14" }]],
    INCOMPLETE: [
      ["circle", { cx: 12, cy: 12, r: 10 }],
      ["line", { x1: 12, x2: 12, y1: 8, y2: 12 }],
      ["line", { x1: 12, x2: 12.01, y1: 16, y2: 16 }],
    ],
  };

  // ใช้คำตามคำอภิธานศัพท์ใน 01-SA (สถานะการทำงาน)
  static STATUS = {
    OK:         { cls: "badge-ok",         text: "ครบ 8 ชม." },
    SHORT:      { cls: "badge-short",      text: "ไม่ครบ 8 ชม." },
    INCOMPLETE: { cls: "badge-incomplete", text: "ข้อมูลยังไม่ครบ" },
  };

  static icon(status) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    for (const [tag, attrs] of StatusBadge.ICONS[status]) {
      const shape = document.createElementNS(SVG_NS, tag);
      for (const [k, v] of Object.entries(attrs)) shape.setAttribute(k, v);
      svg.appendChild(shape);
    }
    return svg;
  }

  static create(status, extra = "") {
    const s = StatusBadge.STATUS[status];
    return el("span", { class: "badge " + s.cls }, StatusBadge.icon(status), s.text + extra);
  }
}

class ReportTable {
  static COLUMNS = [
    ["วันที่", ""],
    ["ชื่อ", ""],
    ["เวลาเข้างาน", "col-num"],
    ["เวลาออกงาน", "col-num"],
    ["สถานะ", ""],
    ["รูปถ่าย", ""],
  ];

  // วันล่าสุดอยู่บน แล้วในวันเดียวกัน เรื่องที่ต้องตามขึ้นก่อน: ข้อมูลยังไม่ครบ → ไม่ครบ 8 ชม. → ครบ แล้วเรียงตามชื่อ
  static RANK = { INCOMPLETE: 0, SHORT: 1, OK: 2 };

  static sorted(rows) {
    return [...rows].sort((a, b) =>
      b.date.localeCompare(a.date) ||
      ReportTable.RANK[a.status] - ReportTable.RANK[b.status] ||
      a.name.localeCompare(b.name, "th"));
  }

  constructor(container) {
    this.container = container;
    this.rowSeq = 0;
  }

  // UC7: รูปประกอบของแต่ละรายการ
  photoFigure(ev, name) {
    const label = ev.type === "in" ? "เข้างาน" : "ออกงาน";
    const time = ev.recorded_at.slice(11, 16) + " น.";
    const img = el("img", { class: "photo", src: "/photos/" + encodeURIComponent(ev.photo_path), alt: `${name} ${label} ${time}`, loading: "lazy" });
    img.addEventListener("error", () => {
      const ageDays = (Date.now() - new Date(ev.recorded_at)) / 86400000;
      const why = ageDays > PHOTO_RETENTION_DAYS ? "รูปที่เก่ากว่า 1 ปีจะถูกลบตามนโยบาย" : "ไฟล์รูปหายไปจากเครื่องเซิร์ฟเวอร์";
      img.replaceWith(el("div", { class: "missing" }, el("span", {}, el("strong", { text: "ไม่พบรูป" }), el("br"), why)));
    });
    return el("figure", { class: "shot" }, img, el("figcaption", { class: "caption" }, `${label} `, el("strong", { class: "num", text: time })));
  }

  // ค่าที่ยังไม่มี: ขีดให้ตาเห็น + ข้อความเต็มให้ screen reader (ขีดเปล่าๆ อ่านออกเสียงไม่รู้เรื่อง)
  static empty(spoken) {
    return el("span", {}, el("span", { "aria-hidden": "true", text: "—" }), el("span", { class: "visually-hidden", text: spoken }));
  }

  personRows(r, colCount) {
    const detailId = "detail-" + this.rowSeq++;
    const photoLabel = `ดูรูป ${r.events.length} รูป`;
    const btn = el("button", { class: "photos-btn", type: "button", "aria-expanded": "false", "aria-controls": detailId, "aria-label": `${photoLabel} ของ${r.name}`, text: photoLabel });
    // label = ป้ายกำกับเหนือค่า แสดงเฉพาะจอแคบ (บนจอกว้างใช้หัวคอลัมน์แทน)
    const cell = (cls, label, content) => {
      const td = el("td", { class: cls, role: "cell", ...(label ? { "data-label": label } : {}) });
      if (typeof content === "string") td.textContent = content; else td.append(content);
      return td;
    };
    const tr = el("tr", { class: "person", role: "row" },
      cell("c-date num", "วันที่", DateText.thai(r.date)),
      cell("c-name", null, el("strong", { text: r.name })),
      cell("c-in col-num num", "เข้างาน", r.first_in ? r.first_in + " น." : ReportTable.empty("ไม่มีเวลาเข้างาน")),
      cell("c-out col-num num", "ออกงาน", r.last_out ? r.last_out + " น." : ReportTable.empty("ยังไม่ออกงาน")),
      cell("c-status", null, StatusBadge.create(r.status)),
      cell("c-photos", null, btn),
    );
    const detail = el("tr", { class: "detail", id: detailId, role: "row", hidden: "" },
      el("td", { role: "cell", colspan: colCount }, el("div", { class: "photos" }, ...r.events.map((ev) => this.photoFigure(ev, r.name)))));
    btn.addEventListener("click", () => {
      const open = detail.hidden;
      detail.hidden = !open;
      btn.setAttribute("aria-expanded", String(open));
    });
    return [tr, detail];
  }

  render(rows) {
    const cols = ReportTable.COLUMNS;
    if (rows.length === 0) {
      this.container.replaceChildren(el("div", { class: "empty" },
        el("strong", { text: "ไม่มีการบันทึกเวลาในช่วงที่เลือก" }),
        el("span", { class: "muted", text: "ลองขยายช่วงวันที่ หรือเปลี่ยนพนักงานเป็น “ทุกคน”" })));
      return;
    }

    // ตารางแสดงเป็นบล็อกบนจอแคบ ใส่ role ชัดเจนเพื่อให้ screen reader ยังอ่านเป็นตารางเหมือนเดิม
    const table = el("table", { role: "table" },
      el("caption", { class: "visually-hidden", text: "สรุปเวลาเข้า-ออกงาน กดปุ่มดูรูปเพื่อดูรูปประกอบ" }),
      el("thead", { role: "rowgroup" }, el("tr", { role: "row" },
        ...cols.map(([text, cls]) => el("th", { scope: "col", role: "columnheader", class: cls, text })))));

    table.appendChild(el("tbody", { role: "rowgroup" }, ...ReportTable.sorted(rows).flatMap((r) => this.personRows(r, cols.length))));
    this.container.replaceChildren(table);
  }
}

class BossPage {
  constructor(api, notice, table) {
    this.api = api;
    this.notice = notice;
    this.table = table;
    this.latestRequest = 0;
  }

  async init() {
    this.bindEvents();
    const today = DateText.localISODate(new Date());
    $("from").value = today;  // UC5: ค่าเริ่มต้นคือวันนี้
    $("to").value = today;
    try {
      for (const e of await this.api.request("/api/employees")) $("employee").appendChild(el("option", { value: e.id, text: e.name }));
    } catch (err) {
      this.notice.show(err.message);
    }
    this.load();
  }

  bindEvents() {
    // เลือกช่วงลัด = โหลดทันที, เลือก "กำหนดเอง" = แสดงช่องวันที่ แล้วรอกดปุ่ม
    $("period").addEventListener("change", () => this.onPeriodChange());
    $("employee").addEventListener("change", () => this.load());
    $("logout-btn").addEventListener("click", () => this.onLogout());
    $("filters").addEventListener("submit", (e) => {
      e.preventDefault();
      this.load();
    });
  }

  async onLogout() {
    try {
      await this.api.request("/api/auth/logout", { method: "POST" });
    } catch (err) {
      this.notice.show(err.message);
      return;
    }
    location.replace("/login");
  }

  onPeriodChange() {
    const period = $("period").value;
    const custom = period === "custom";
    $("filters").hidden = !custom;
    if (custom) {
      $("from").focus();
      return;
    }
    [$("from").value, $("to").value] = BossPage.presetRange(period);
    this.load();
  }

  static presetRange(preset) {
    const day = (offset) => {
      const d = new Date();
      d.setDate(d.getDate() - offset);
      return DateText.localISODate(d);
    };
    if (preset === "today") return [day(0), day(0)];
    if (preset === "yesterday") return [day(1), day(1)];
    return [day(Number(preset) - 1), day(0)];  // "7" / "30" = รวมวันนี้
  }

  renderHead(rows, filter) {
    const today = DateText.localISODate(new Date());
    const single = filter.from === filter.to;
    const title = el("h2", { id: "result-title" });
    if (single && filter.from === today) title.append(el("span", { class: "eyebrow", text: "วันนี้" }));
    title.append(single
      ? DateText.thai(filter.from, DateText.LONG)
      : `${DateText.thai(filter.from)} ถึง ${DateText.thai(filter.to)}`);
    if (filter.employeeName) title.append(el("span", { class: "eyebrow", text: `ของ ${filter.employeeName}` }));
    $("result-title").replaceWith(title);

    // KPI row: ตัวเลขเป็นตัวหลัก ชื่อสถานะอยู่ใต้ตัวเลข (ไม่ใช้ป้ายสีทึบ เพื่อไม่ให้สับสนกับป้ายสถานะรายคน)
    const counts = { OK: 0, SHORT: 0, INCOMPLETE: 0 };
    for (const r of rows) counts[r.status]++;
    $("counts").replaceChildren(...Object.keys(StatusBadge.STATUS).map((key) => {
      const s = StatusBadge.STATUS[key];
      return el("div", { class: `kpi kpi-${key.toLowerCase()}${counts[key] === 0 ? " is-zero" : ""}` },
        el("dt", {}, StatusBadge.icon(key), s.text),
        el("dd", { class: "num" }, String(counts[key]), el("small", { text: " คน" })));
    }));
  }

  // ตรวจช่วงวันที่ที่กำหนดเองก่อนส่ง (เซิร์ฟเวอร์ตรวจซ้ำ) — คืนจริงถ้าส่งได้
  validateRange() {
    const from = $("from");
    const to = $("to");
    const problems = [];
    if (!from.value) problems.push([from, "เลือกวันที่เริ่มต้น"]);
    if (!to.value) problems.push([to, "เลือกวันที่สิ้นสุด"]);
    if (problems.length === 0) {
      const days = (new Date(to.value) - new Date(from.value)) / 86400000;
      if (days < 0) problems.push([to, "วันที่สิ้นสุดต้องไม่ก่อนวันที่เริ่มต้น"]);
      else if (days >= 366) problems.push([to, "เลือกช่วงวันที่ไม่เกิน 1 ปี"]);
    }
    for (const input of [from, to]) new FieldError(input).clear();
    for (const [input, message] of problems) new FieldError(input).show(message);
    if (problems.length > 0) problems[0][0].focus();
    return problems.length === 0;
  }

  async load() {
    this.notice.clear();
    if (!this.validateRange()) return;
    const select = $("employee");
    const filter = {
      from: $("from").value,
      to: $("to").value,
      employeeId: select.value,
      employeeName: select.value ? select.selectedOptions[0].textContent : "",
    };
    const requestId = ++this.latestRequest;
    try {
      let rows;
      if (filter.from === filter.to && !filter.employeeId) {
        // FR5: รายงานรายวันไม่มี field date (ตามสัญญา) — วันที่คือวันที่ที่ขอ
        rows = (await this.api.request("/api/report/daily?date=" + filter.from)).map((r) => ({ ...r, date: filter.from }));
      } else {
        const q = new URLSearchParams({ from: filter.from, to: filter.to });  // FR6
        if (filter.employeeId) q.set("employee_id", filter.employeeId);
        rows = await this.api.request("/api/report/range?" + q);
      }
      if (requestId !== this.latestRequest) return;  // มีการกรองใหม่ระหว่างรอ ทิ้งผลเก่า
      this.renderHead(rows, filter);
      this.table.render(rows);
    } catch (err) {
      if (requestId === this.latestRequest) this.notice.show(err.message);
    }
  }
}

new BossPage(new ApiClient(NETWORK_ERROR), new Notice(), new ReportTable($("table-wrap"))).init();
