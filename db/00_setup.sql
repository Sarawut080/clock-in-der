-- ตั้งค่าครั้งแรก: สร้าง user ของแอป + ฐานข้อมูลจริง + ฐานข้อมูลสำหรับทดสอบ
-- รันด้วยสิทธิ์ postgres ครั้งเดียว (รันซ้ำได้ ไม่พัง):
--   & "C:\Program Files\PostgreSQL\17\bin\psql.exe" -p 5433 -U postgres -f db\00_setup.sql
-- (PostgreSQL 17 ฟังที่พอร์ต 5433, 18 ที่ 5432 — ใช้ตัวไหนให้ใช้พอร์ตและ DATABASE_URL ใน .env ให้ตรงกัน)
-- psql จะถามรหัสของ postgres ก่อน แล้วถามรหัสใหม่ของ user clockin 2 ครั้ง (พิมพ์แล้วไม่ขึ้นบนจอ)
-- ไม่ใช้ pgAdmin Query Tool เพราะ CREATE DATABASE รันรวมกับคำสั่งอื่นในชุดเดียวไม่ได้

\encoding UTF8
\set ON_ERROR_STOP on

-- user ของแอป: เข้าสู่ระบบได้ แต่ไม่ใช่ superuser สร้าง database/role อื่นไม่ได้
SELECT 'CREATE ROLE clockin LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'clockin') \gexec
ALTER ROLE clockin WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;

\echo
\echo 'Set a password for database user "clockin" (put the same one in .env):'
\password clockin

-- ฐานข้อมูลจริง และฐานข้อมูลสำหรับชุดทดสอบ (ทดสอบล้างข้อมูลทุกครั้ง ห้ามใช้ตัวจริง)
SELECT 'CREATE DATABASE clockin OWNER clockin ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'clockin') \gexec
SELECT 'CREATE DATABASE clockin_test OWNER clockin ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'clockin_test') \gexec

-- ไม่ให้ user อื่น (PUBLIC) เชื่อมต่อเข้ามาโดยปริยาย
REVOKE CONNECT ON DATABASE clockin FROM PUBLIC;
REVOKE CONNECT ON DATABASE clockin_test FROM PUBLIC;
GRANT CONNECT ON DATABASE clockin, clockin_test TO clockin;

\echo
\echo 'Done. Next: copy .env.example to .env, fill in the password, then run: python -m app.cli init-db'
