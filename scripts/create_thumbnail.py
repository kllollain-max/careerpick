#!/usr/bin/env python3
"""Generate a legible CareerPick job card without shortening its facts.

Usage: python scripts/create_thumbnail.py '{"id":"123","org":"기관명","title":"채용","count":16,"due":"2026-11-05"}'
"""
from functools import lru_cache
from datetime import datetime
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
COMPACT_LAYOUT_VERSION = "careerpick-single-main-card-v2"
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


def _compact_card_fields(job):
    """Keep the verified values; only reformat an unambiguous ISO deadline.

    This renderer is deliberately not a fact summarizer. Long qualification
    text must be summarized and reviewed by the writer before it reaches here.
    A field that cannot fit remains a layout error, never a shortened fact.
    """
    if not isinstance(job, dict):
        raise ThumbnailLayoutError("A job dictionary is required")
    fields = {}
    for key in ("org", "title", "employment", "deadline_label"):
        value = clean(job.get(key), fallback="")
        if not value:
            raise ThumbnailLayoutError(f"{key}: a verified value is required")
        fields[key] = value
    count = job.get("count")
    if count is not None and not (
        (type(count) is int and count > 0)
        or (isinstance(count, str) and re.fullmatch(r"(?:[1-9][0-9]*|0{2,})명?", count.strip()))
    ):
        raise ThumbnailLayoutError("count: expected a positive or explicitly unspecified count")
    fields["count"] = _count_text(count) if count is not None else "인원 공고 확인"
    fields["restriction"] = clean(job.get("restriction"), fallback="")
    # No URL, domain, hashtag or obfuscated URL may be placed on this card.
    # Numeric dates (11.18) are not mistaken for domain names.
    links = re.compile(
        r"(?i)(?:https?\s*[:：]|hxxps?|www\s*[.．]|"
        r"[a-z0-9-]+\s*[.．]\s*(?:com|net|org|kr|io|co|me|app|ai|dev|info|ly)\b|"
        r"[a-z0-9-]+\s*\[dot\]\s*[a-z]{2,}|[#＃])"
    )
    if any(links.search(value) for value in fields.values()):
        raise ThumbnailLayoutError("Card fields must not contain links or hashtags")
    label = fields["deadline_label"]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2}(?::\d{2})?)?", label):
        try:
            stamp = datetime.fromisoformat(label)
        except ValueError as exc:
            raise ThumbnailLayoutError("deadline_label: invalid ISO date/time") from exc
        # Dates and clock precision are preserved. Date-only never means 23:59.
        clock = label[11:]
        fields["deadline_label"] = f"{stamp.month}월 {stamp.day}일" + (f" {clock}" if clock else "")
    return fields


def generate_compact_card(job, destination):
    """Render one mobile-readable card for the single-main editorial policy.

    The job, employment type and scoped count are larger than the institution.
    This path has no CTA banner and cannot insert a QR image or remote asset.
    Metadata is a layout check, not a claim that human visual review occurred.
    """
    fields = _compact_card_fields(job)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", IMAGE_SIZE, "#F3F7FC")
    draw = ImageDraw.Draw(im)
    navy, blue, muted = "#102C50", "#0759B4", "#41556E"

    _draw_fitted(draw, "커리어픽", (70, 58, 1010, 103),
                 size=30, minimum=30, max_lines=1, fill=blue, field="brand")
    draw.rounded_rectangle((70, 127, 1010, 133), radius=3, fill="#CEDFF3")
    _draw_fitted(draw, fields["title"], (70, 174, 1010, 411),
                 size=96, minimum=78, max_lines=2, fill=navy,
                 vertical="top", field="title")
    _draw_fitted(draw, fields["employment"] + " · " + fields["count"],
                 (70, 420, 1010, 590), size=76, minimum=68, max_lines=2,
                 fill=blue, vertical="top", field="employment_and_count")
    _draw_fitted(draw, fields["org"], (70, 631, 1010, 761),
                 size=56, minimum=48, max_lines=2, fill=navy,
                 vertical="top", field="org")

    draw.rounded_rectangle((48, 798, 1032, 1032), radius=26, fill="white")
    _draw_fitted(draw, "접수 마감", (78, 820, 1002, 860),
                 size=30, minimum=30, max_lines=1, fill=muted, field="deadline_heading")
    _draw_fitted(draw, fields["deadline_label"], (78, 881, 1002, 951),
                 size=56, minimum=54, max_lines=1, fill=navy, field="deadline")
    if fields["restriction"]:
        _draw_fitted(draw, fields["restriction"], (78, 975, 1002, 1021),
                     size=40, minimum=38, max_lines=1, fill=muted, field="restriction")

    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".compact-", suffix=".jpg", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        im.save(temporary, "JPEG", quality=95, subsampling=0, optimize=True, progressive=False)
        metadata = verify_thumbnail(temporary)
        if metadata["file_size_bytes"] < 10_000:
            raise ThumbnailValidationError("Generated image is unexpectedly small")
        metadata.update({
            "layout_version": COMPACT_LAYOUT_VERSION,
            "rendered_fields": fields,
            "preview_width": 360,
            "minimum_core_font_at_preview_px": 54 / 3,
            "human_visual_review": "required",
        })
        temporary.replace(destination)
        return metadata
    finally:
        temporary.unlink(missing_ok=True)


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
