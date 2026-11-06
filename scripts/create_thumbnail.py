#!/usr/bin/env python3
"""Generate a legible CareerPick job card without shortening its facts.

Usage: python scripts/create_thumbnail.py '{"id":"123","org":"기관명","title":"채용","count":16,"due":"2026-11-05"}'
"""
from functools import lru_cache
import json
import re
import sys
import tempfile
import unicodedata
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "threads-images"
IMAGE_SIZE = (1080, 1080)
# A conservative decimal MB limit also fits an 8 MiB upload limit.
MAX_IMAGE_BYTES = 8_000_000
CTA = "자세한 채용정보는 프로필 링크를 확인하세요."
FONT_PATHS = [
    "/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/local/share/fonts/NotoSansCJKkr-Bold.otf",
    "/usr/local/share/fonts/NotoSansCJKkr-Regular.otf",
]


class ThumbnailLayoutError(ValueError):
    """A complete field cannot be rendered at a readable size."""


class ThumbnailValidationError(ValueError):
    """The image is not a fully decodable, uploadable CareerPick JPEG."""


@lru_cache(maxsize=96)
def font(size):
    for path in FONT_PATHS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise RuntimeError("Install fonts-nanum or fonts-noto-cjk for Korean thumbnails")


def clean(value, fallback="공고 확인"):
    if value is None:
        return fallback
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ThumbnailLayoutError("Thumbnail fields must be text or integer values")
    s = unicodedata.normalize("NFC", re.sub(r"\s+", " ", str(value)).strip())
    if any(unicodedata.category(ch) in {"Cc", "Cf", "Cs"} for ch in s):
        raise ThumbnailLayoutError("Thumbnail field contains invisible control characters")
    return s if s else fallback


def _width(draw, text, f):
    left, _, right, _ = draw.textbbox((0, 0), text, font=f)
    return right - left


def wrap(draw, text, f, max_width, max_lines):
    """Wrap complete words where possible; never replace content with an ellipsis."""
    lines, current = [], ""

    def append(line):
        if line:
            lines.append(line)
        if len(lines) > max_lines:
            raise ThumbnailLayoutError("Field exceeds its available line count")

    for word in text.split(" "):
        candidate = f"{current} {word}" if current else word
        if _width(draw, candidate, f) <= max_width:
            current = candidate
            continue
        append(current)
        current = ""
        if _width(draw, word, f) <= max_width:
            current = word
            continue
        # Korean titles and identifiers can have no spaces. All characters are
        # retained across the line break, including the final qualification.
        for ch in word:
            if _width(draw, ch, f) > max_width:
                raise ThumbnailLayoutError("A glyph is wider than its text box")
            if current and _width(draw, current + ch, f) > max_width:
                append(current)
                current = ch
            else:
                current += ch
    append(current)
    return lines


def _assert_supported(text, f):
    missing = f.getmask("\U0010ffff")
    missing_shape = (missing.size, bytes(missing))
    for ch in set(text) - {" "}:
        glyph = f.getmask(ch)
        if (glyph.size, bytes(glyph)) == missing_shape:
            raise ThumbnailLayoutError("Selected font cannot display a supplied character")


def _draw_fitted(draw, text, box, *, size, minimum, max_lines, fill,
                 align="left", vertical="middle", field="text"):
    """Fit all text inside the box, or stop before any image is published."""
    text = clean(text)
    if len(text) > 1000:
        raise ThumbnailLayoutError(f"{field}: complete text is too long for the card")
    x0, y0, x1, y1 = box
    _assert_supported(text, font(minimum))
    for candidate_size in range(size, minimum - 1, -1):
        f = font(candidate_size)
        try:
            lines = wrap(draw, text, f, x1 - x0, max_lines)
        except ThumbnailLayoutError:
            continue
        line_height = max(
            candidate_size,
            *(draw.textbbox((0, 0), line, font=f)[3]
              - draw.textbbox((0, 0), line, font=f)[1] for line in lines),
        )
        gap = max(5, round(candidate_size * 0.16))
        height = line_height * len(lines) + gap * (len(lines) - 1)
        if height > y1 - y0:
            continue
        y = y0 if vertical == "top" else y0 + (y1 - y0 - height) / 2
        for line in lines:
            left, top, right, bottom = draw.textbbox((0, 0), line, font=f)
            width = right - left
            x = x0 if align == "left" else x0 + (x1 - x0 - width) / 2
            # Compensate for the font's bearings: the ink itself, not only its
            # nominal origin, must stay inside the allocated rectangle.
            position = (x - left, y - top)
            bounds = draw.textbbox(position, line, font=f)
            if (bounds[0] < x0 or bounds[1] < y0
                    or bounds[2] > x1 or bounds[3] > y1):
                raise ThumbnailLayoutError(f"{field}: text would be clipped")
            draw.text(position, line, font=f, fill=fill)
            y += line_height + gap
        return height
    raise ThumbnailLayoutError(f"{field}: complete text does not fit at a readable size")


def _count_text(value):
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return f"{value}명"
    if isinstance(value, str):
        value = clean(value)
        # Preserve unspecified counts such as '00명'; never parse them as zero.
        return f"{value}명" if re.fullmatch(r"[0-9]+", value) else value
    return "공고 확인"


def verify_thumbnail(path):
    """Fully decode a normal RGB JPEG and return its validated upload metadata."""
    path = Path(path)
    try:
        file_size = path.stat().st_size
        if not path.is_file() or not 0 < file_size <= MAX_IMAGE_BYTES:
            raise ThumbnailValidationError("Thumbnail is empty or exceeds 8 MB")
        with Image.open(path) as check:
            if (check.format != "JPEG" or check.size != IMAGE_SIZE
                    or check.mode != "RGB" or getattr(check, "n_frames", 1) != 1):
                raise ThumbnailValidationError("Expected a 1080x1080 RGB JPEG")
            check.verify()
        # verify() does not decode all JPEG scan data. Reopen and load pixels so
        # truncated or corrupt payloads cannot pass on a valid header alone.
        with Image.open(path) as check:
            check.load()
    except ThumbnailValidationError:
        raise
    except (OSError, ValueError, SyntaxError) as exc:
        raise ThumbnailValidationError("Thumbnail could not be fully decoded") from exc
    return {
        "valid": True,
        "format": "JPEG",
        "width": IMAGE_SIZE[0],
        "height": IMAGE_SIZE[1],
        "mode": "RGB",
        "file_size_bytes": file_size,
    }


def generate(job):
    if not isinstance(job, dict):
        raise ThumbnailLayoutError("A job dictionary is required")
    OUT.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", IMAGE_SIZE, "#F2F8FF")
    d = ImageDraw.Draw(im)
    navy, blue, muted = "#132B4E", "#1264C8", "#52647B"
    d.rounded_rectangle((40, 38, 1040, 160), radius=26, fill=navy)
    _draw_fitted(d, "CAREERPICK  |  채용정보", (75, 65, 1005, 133),
                 size=46, minimum=40, max_lines=1, fill="white", field="brand")
    org_height = _draw_fitted(
        d, clean(job.get("org")), (68, 204, 1012, 308),
        size=46, minimum=30, max_lines=2, fill=blue, vertical="top", field="org",
    )
    _draw_fitted(d, clean(job.get("title")), (68, 204 + org_height + 28, 1012, 540),
                 size=65, minimum=34, max_lines=4, fill=navy,
                 vertical="top", field="title")
    d.rounded_rectangle((44, 570, 1036, 932), radius=30, fill="white")
    fields = [
        ("채용인원", _count_text(job.get("count"))),
        # Use the verified label verbatim; never invent an end-of-day time.
        ("접수마감", clean(job.get("deadline_label") or job.get("due"))),
        ("고용형태", clean(job.get("employment"))),
        ("근무지역", clean(job.get("location"))),
    ]
    for i, (label, value) in enumerate(fields):
        yy = 588 + i * 82
        _draw_fitted(d, label, (80, yy, 278, yy + 70),
                     size=34, minimum=32, max_lines=1, fill=muted, field=label)
        _draw_fitted(d, value, (304, yy, 1000, yy + 70),
                     size=43, minimum=28, max_lines=2, fill=navy, field=label)
    d.rounded_rectangle((44, 951, 1036, 1042), radius=20, fill=blue)
    _draw_fitted(d, CTA, (72, 959, 1008, 1034),
                 size=36, minimum=32, max_lines=2, fill="white", align="center", field="CTA")
    identifier = re.sub(r"[^A-Za-z0-9_-]", "_", str(job.get("id", "job")))[:70]
    path = OUT / (identifier + ".jpg")
    # Never leave a partial new image at the public path if save or validation
    # fails. Existing images are replaced only after the new image is verified.
    with tempfile.NamedTemporaryFile(dir=OUT, prefix=f".{identifier}-", suffix=".jpg", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        im.save(temporary, "JPEG", quality=95, subsampling=0, optimize=True, progressive=False)
        metadata = verify_thumbnail(temporary)
        if metadata["file_size_bytes"] < 10_000:
            raise ThumbnailValidationError("Generated image is unexpectedly small")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


if __name__ == "__main__":
    print(generate(json.loads(sys.argv[1])))
