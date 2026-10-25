"""คำสั่งดูแลระบบ (ต้องตั้ง DATABASE_URL ใน .env ก่อน) รันที่โฟลเดอร์โปรเจกต์:

    .venv\\Scripts\\python.exe -m app.cli init-db            สร้างตารางที่ยังไม่มี (แอปก็สร้างให้เองตอนเริ่ม)
    .venv\\Scripts\\python.exe -m app.cli seed-demo          ใส่พนักงานเดโม 5 คน (PIN 123456) ลงฐานข้อมูลที่ว่างเปล่า
    .venv\\Scripts\\python.exe -m app.cli reset-pin "ชื่อ"    ตั้ง PIN ใหม่ให้พนักงานที่ลืม (ถามรหัสใหม่แบบไม่แสดงบนจอ)
    .venv\\Scripts\\python.exe -m app.cli wipe-data          ดูว่าจะลบอะไร (ยังไม่ลบ) · เพิ่ม --confirm <ชื่อฐานข้อมูล> [--photos] เพื่อลบจริง
"""
import argparse
import getpass
import sys

from .auth import PIN_PATTERN, clean_name
from .container import Container
from .mock_store import DemoSeeder


def _container() -> Container:
    container = Container.from_env()
    if container.database is None:
        sys.exit("ยังไม่ได้ตั้ง DATABASE_URL — คัดลอก .env.example เป็น .env แล้วใส่รหัสก่อน (ดู README)")
    return container


def init_db(_: argparse.Namespace) -> None:
    c = _container()
    c.database.open()
    try:
        c.database.ensure_schema()
    finally:
        c.database.close()
    print("พร้อมแล้ว: ตาราง employees, attendance, index และ trigger append-only")


def seed_demo(_: argparse.Namespace) -> None:
    c = _container()
    c.database.open()
    try:
        c.database.ensure_schema()
        if c.employees.count() or c.attendance.count():
            sys.exit("ฐานข้อมูลนี้มีข้อมูลแล้ว — seed-demo ใช้ได้กับฐานข้อมูลว่างเปล่าเท่านั้น (กันเดโมปนข้อมูลจริง)")
        DemoSeeder(c.employees, c.attendance, c.clock, c.upload_dir, c.hasher.hash).seed()
    finally:
        c.database.close()
    print(f"ใส่ข้อมูลเดโมแล้ว: พนักงาน {len(DemoSeeder.EMPLOYEES)} คน PIN {DemoSeeder.DEMO_PIN}")


def reset_pin(args: argparse.Namespace) -> None:
    c = _container()
    c.database.open()
    try:
        c.database.ensure_schema()
        emp = c.employees.find_by_name(clean_name(args.name))
        if emp is None:
            sys.exit(f"ไม่พบพนักงานชื่อ {args.name!r}")
        pin = getpass.getpass(f"PIN ใหม่ของ {emp.name} (ตัวเลข 6 หลัก): ")
        if not PIN_PATTERN.fullmatch(pin):
            sys.exit("PIN ต้องเป็นตัวเลข 6 หลัก")
        if getpass.getpass("ใส่ PIN อีกครั้ง: ") != pin:
            sys.exit("PIN 2 ช่องไม่ตรงกัน")
        c.employees.set_pin_hash(emp.id, c.hasher.hash(pin))
    finally:
        c.database.close()
    print(f"ตั้ง PIN ใหม่ให้ {emp.name} แล้ว (ผู้ที่ล็อกอินค้างอยู่ยังใช้งานต่อได้จนกว่าจะรีสตาร์ทเซิร์ฟเวอร์หรือออกจากระบบ)")


def wipe_data(args: argparse.Namespace) -> None:
    c = _container()
    c.database.open()
    try:
        c.database.ensure_schema()
        name = c.database.database_name()
        people, events = c.employees.count(), c.attendance.count()
        photos = [p for p in c.upload_dir.glob("*") if p.is_file() and p.name != ".gitkeep"] if args.photos else []
        summary = f"ฐานข้อมูล {name!r}: พนักงาน {people} คน, รายการเวลา {events} รายการ" + (
            f", ไฟล์รูปใน {c.upload_dir.name}/ {len(photos)} ไฟล์" if args.photos else " (ไฟล์รูปไม่ถูกลบ — เพิ่ม --photos ถ้าต้องการ)"
        )
        if args.confirm != name:
            sys.exit(
                f"จะลบถาวร: {summary}\n"
                f"ถ้าแน่ใจ รันซ้ำพร้อมพิมพ์ชื่อฐานข้อมูลยืนยัน:  python -m app.cli wipe-data --confirm {name}"
                + (" --photos" if args.photos else "")
            )
        c.database.wipe_all()
        for photo in photos:
            photo.unlink(missing_ok=True)
    finally:
        c.database.close()
    print(f"ล้างแล้ว: {summary}\nพนักงานคนต่อไปที่ลงทะเบียนจะได้ id 1 ใหม่")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db").set_defaults(func=init_db)
    sub.add_parser("seed-demo").set_defaults(func=seed_demo)
    wipe = sub.add_parser("wipe-data", help="ล้างข้อมูลทั้งหมด (ต้องพิมพ์ชื่อฐานข้อมูลยืนยัน)")
    wipe.add_argument("--confirm", default="", help="ชื่อฐานข้อมูลที่จะล้าง — ต้องตรงกับฐานข้อมูลที่ DATABASE_URL ชี้อยู่")
    wipe.add_argument("--photos", action="store_true", help="ลบไฟล์รูปในโฟลเดอร์ uploads/ ด้วย")
    wipe.set_defaults(func=wipe_data)
    reset = sub.add_parser("reset-pin")
    reset.add_argument("name", help="ชื่อ-นามสกุลของพนักงาน")
    reset.set_defaults(func=reset_pin)
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ConnectionError as e:  # ต่อฐานข้อมูลไม่ได้: แสดงสาเหตุสั้นๆ ไม่โยน traceback ยาว
        sys.exit(str(e))


if __name__ == "__main__":
    main()
