import struct
import zlib
from datetime import datetime, timedelta

from app.mock_store import BKK, ServerClock

# ไฟล์ที่ระบบต้องยอมรับ: ขึ้นต้นด้วย magic bytes ของ JPEG
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def tiny_png(width: int = 8, height: int = 8) -> bytes:
    """PNG จริงที่เบราว์เซอร์แสดงได้ สร้างด้วย stdlib (ไม่ต้องพึ่ง Pillow)"""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\x2f\x6f\x7f" * width for _ in range(height))  # แถวละ filter byte + RGB
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


class FakeClock(ServerClock):
    """นาฬิกาที่เดินเอง — ใช้ทดสอบข้ามวัน/กฎ BR3 โดยไม่ต้องรอ"""

    def __init__(self, start: datetime | None = None):
        self.current = start or datetime(2026, 10, 25, 9, 0, 0, tzinfo=BKK)

    def now(self) -> datetime:
        return self.current

    def advance(self, **kwargs) -> None:
        self.current += timedelta(**kwargs)
