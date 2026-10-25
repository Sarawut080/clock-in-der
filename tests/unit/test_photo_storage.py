import pytest

from app.errors import ApiError
from app.services import PhotoStorage
from tests.helpers import JPEG, tiny_png


@pytest.mark.parametrize(
    "content,ext",
    [
        (JPEG, ".jpg"),
        (tiny_png(), ".png"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", ".webp"),
        (b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00", ".heic"),
        (b"\x00\x00\x00\x18ftypmif1\x00\x00\x00\x00", ".heic"),
        (b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", None),
        (b"<html><script>alert(1)</script></html>", None),
        (b"GIF89a....", None),
        (b"MZ\x90\x00", None),
        (b"", None),
        (b"\xff\xd8", None),  # สั้นเกินไป ไม่ใช่ JPEG ครบ
        (b"RIFF\x00\x00\x00\x00WAVEfmt ", None),
        (b"\x00\x00\x00\x18ftypmp42", None),  # วิดีโอ MP4 ไม่ใช่รูป
    ],
)
def test_detect_extension_uses_bytes_not_filename(content, ext):
    assert PhotoStorage.detect_extension(content) == ext


def test_save_names_file_by_detected_type(tmp_path):
    storage = PhotoStorage(tmp_path)
    name = storage.save(7, tiny_png())
    assert name.startswith("7_") and name.endswith(".png")
    assert (tmp_path / name).read_bytes() == tiny_png()


def test_save_rejects_non_image_and_leaves_no_file(tmp_path):
    with pytest.raises(ApiError) as e:
        PhotoStorage(tmp_path).save(1, b"<svg/>")
    assert e.value.code == "INVALID_PHOTO"
    assert list(tmp_path.iterdir()) == []


def test_save_rejects_oversize(tmp_path):
    with pytest.raises(ApiError) as e:
        PhotoStorage(tmp_path).save(1, JPEG + b"\x00" * PhotoStorage.MAX_BYTES)
    assert e.value.code == "PHOTO_TOO_LARGE"
    assert list(tmp_path.iterdir()) == []


def test_save_accepts_exactly_max(tmp_path):
    content = JPEG + b"\x00" * (PhotoStorage.MAX_BYTES - len(JPEG))
    assert len(content) == PhotoStorage.MAX_BYTES
    assert PhotoStorage(tmp_path).save(1, content).endswith(".jpg")


def test_filenames_are_unique(tmp_path):
    s = PhotoStorage(tmp_path)
    assert len({s.save(1, JPEG) for _ in range(20)}) == 20
