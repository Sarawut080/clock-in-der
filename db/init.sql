-- Schema ตาม 02-contract.md ข้อ 1 — รันซ้ำได้ (แอปรันเองทุกครั้งที่เริ่ม หรือ python -m app.cli init-db)

-- พนักงาน
CREATE TABLE IF NOT EXISTS employees (
    id          SERIAL PRIMARY KEY,
    name        TEXT        NOT NULL,
    role        TEXT        NOT NULL DEFAULT 'worker',   -- 'worker' | 'boss' (v1 ยังไม่ใช้แยกสิทธิ์ — 01-SA D9)
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    pin_hash    TEXT,                                    -- PBKDF2-SHA256 "salt_hex$hash_hex" (BR6) ห้ามเก็บ PIN จริง
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE employees ADD COLUMN IF NOT EXISTS pin_hash TEXT;  -- ฐานข้อมูลที่สร้างก่อนมีระบบเข้าสู่ระบบ

-- ชื่อไม่ซ้ำ (BR8): เทียบหลังตัดช่องว่างหัวท้าย/ยุบช่องว่างซ้ำ และไม่สนตัวพิมพ์เล็ก-ใหญ่
CREATE UNIQUE INDEX IF NOT EXISTS idx_employees_name
    ON employees (lower(regexp_replace(btrim(name), '\s+', ' ', 'g')));

-- เหตุการณ์เข้า-ออกงาน (1 แถว = 1 เหตุการณ์, append-only ตาม BR4)
CREATE TABLE IF NOT EXISTS attendance (
    id           SERIAL      PRIMARY KEY,
    employee_id  INTEGER     NOT NULL REFERENCES employees(id),
    type         TEXT        NOT NULL CHECK (type IN ('in', 'out')),
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now(),     -- เวลาเซิร์ฟเวอร์ (BR2)
    photo_path   TEXT        NOT NULL,                   -- ไม่มีรูป = บันทึกไม่ได้ (BR1)
    note         TEXT
);

CREATE INDEX IF NOT EXISTS idx_attendance_emp_date ON attendance (employee_id, recorded_at);

-- BR4 บังคับที่ฐานข้อมูล: แก้/ลบบันทึกดิบไม่ได้ แม้แก้ผ่าน pgAdmin ก็ถูกปฏิเสธ
-- (ถ้าต้องแก้จริง ให้เพิ่มแถวใหม่ที่อธิบายการแก้ใน note แทน)
CREATE OR REPLACE FUNCTION attendance_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'attendance is append-only (BR4): % is not allowed', TG_OP;
END;
$$;

CREATE OR REPLACE TRIGGER attendance_no_update_delete
    BEFORE UPDATE OR DELETE ON attendance
    FOR EACH ROW EXECUTE FUNCTION attendance_append_only();
