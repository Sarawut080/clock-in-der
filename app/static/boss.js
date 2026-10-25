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
    ["ชื่อ", ""],
    ["เข้างานครั้งแรก", "col-num"],
    ["ออกงานครั้งสุดท้าย", "col-num"],
    ["ชั่วโมงทำงานสะสม", "col-num"],
    ["สถานะ", ""],
  ];

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

  personRows(r, colCount) {
    const detailId = "detail-" + this.rowSeq++;
    const btn = el("button", { class: "name-btn", type: "button", "aria-expanded": "false", "aria-controls": detailId, text: r.name });
    // short = ป้ายสั้นที่แสดงหน้าค่าเฉพาะบนจอแคบ (บนจอกว้างใช้หัวคอลัมน์แทน)
    const cell = (cls, short, content) => {
      const td = el("td", { class: cls, role: "cell", ...(short ? { "data-short": short } : {}) });
      if (typeof content === "string") td.textContent = content; else td.append(content);
      return td;
    };
    const incomplete = r.status === "INCOMPLETE";
    const tr = el("tr", { class: "person", role: "row" },
      cell("c-name", null, btn),
      cell("c-in col-num num", "เข้า", r.first_in ? r.first_in + " น." : "-"),
      r.last_out
        ? cell("c-out col-num num", "ออก", r.last_out + " น.")
        : cell("c-out col-num muted", null, "ยังไม่ออกงาน"),
      cell("c-hours col-num num" + (incomplete ? " is-empty" : ""), null, incomplete ? "-" : DateText.hours(r.worked_minutes)),
      cell("c-status", null, StatusBadge.create(r.status)),
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

  render(rows, grouped) {
    const cols = ReportTable.COLUMNS;
    if (rows.length === 0) {
      this.container.replaceChildren(el("div", { class: "empty" },
        el("strong", { text: "ไม่มีการบันทึกเวลาในช่วงที่เลือก" }),
        el("span", { class: "muted", text: "ลองขยายช่วงวันที่ หรือเปลี่ยนพนักงานเป็น “ทุกคน”" })));
      return;
    }

    // ตารางแสดงเป็นบล็อกบนจอแคบ ใส่ role ชัดเจนเพื่อให้ screen reader ยังอ่านเป็นตารางเหมือนเดิม
    const table = el("table", { role: "table" },
      el("caption", { class: "visually-hidden", text: "สรุปเวลาเข้า-ออกงาน กดชื่อเพื่อดูรูปประกอบ" }),
      el("thead", { role: "rowgroup" }, el("tr", { role: "row" },
        ...cols.map(([text, cls]) => el("th", { scope: "col", role: "columnheader", class: cls, text })))));

    if (!grouped) {
      table.appendChild(el("tbody", { role: "rowgroup" }, ...rows.flatMap((r) => this.personRows(r, cols.length))));
    } else {
      // ช่วงวันที่: แยกกลุ่มตามวัน วันล่าสุดอยู่บน
      const byDate = new Map();
      for (const r of rows) {
        if (!byDate.has(r.date)) byDate.set(r.date, []);
        byDate.get(r.date).push(r);
      }
      for (const date of [...byDate.keys()].sort().reverse()) {
        const head = el("tr", { class: "group", role: "row" },
          el("th", { scope: "rowgroup", role: "rowheader", colspan: cols.length, text: DateText.thai(date, DateText.LONG) }));
        table.appendChild(el("tbody", { role: "rowgroup" }, head, ...byDate.get(date).flatMap((r) => this.personRows(r, cols.length))));
      }
    }
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
    $("filters").addEventListener("submit", (e) => {
      e.preventDefault();
      this.load();
    });
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
    let title = filter.from === filter.to
      ? (filter.from === today ? "วันนี้ " : "") + DateText.thai(filter.from, DateText.LONG)
      : `${DateText.thai(filter.from)} ถึง ${DateText.thai(filter.to)}`;
    if (filter.employeeName) title += ` ของ${filter.employeeName}`;
    $("result-title").textContent = title;

    const counts = { OK: 0, SHORT: 0, INCOMPLETE: 0 };
    for (const r of rows) counts[r.status]++;
    $("counts").replaceChildren(...Object.keys(StatusBadge.STATUS).map((key) => el("li", {}, StatusBadge.create(key, ` ${counts[key]}`))));
  }

  async load() {
    this.notice.clear();
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
      let grouped;
      if (filter.from === filter.to && !filter.employeeId) {
        rows = await this.api.request("/api/report/daily?date=" + filter.from);  // FR5
        grouped = false;
      } else {
        const q = new URLSearchParams({ from: filter.from, to: filter.to });  // FR6
        if (filter.employeeId) q.set("employee_id", filter.employeeId);
        rows = await this.api.request("/api/report/range?" + q);
        grouped = filter.from !== filter.to;
      }
      if (requestId !== this.latestRequest) return;  // มีการกรองใหม่ระหว่างรอ ทิ้งผลเก่า
      this.renderHead(rows, filter);
      this.table.render(rows, grouped);
    } catch (err) {
      if (requestId === this.latestRequest) this.notice.show(err.message);
    }
  }
}

new BossPage(new ApiClient(NETWORK_ERROR), new Notice(), new ReportTable($("table-wrap"))).init();
