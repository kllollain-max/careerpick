#!/usr/bin/env python3
"""Generate a legible CareerPick job card (Pillow required).

Usage: python scripts/create_thumbnail.py '{"id":"123","org":"기관명","title":"채용","count":16,"due":"2026-11-05"}'
"""
import json
import re
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "threads-images"
FONT_PATHS = [
    "/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]

def font(size):
    for path in FONT_PATHS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise RuntimeError("Install fonts-nanum or fonts-noto-cjk for Korean thumbnails")

def clean(value, fallback="공고 확인"):
    s = re.sub(r"\s+", " ", str(value or "")).strip()
    return s if s else fallback

def wrap(draw, text, f, max_width, max_lines):
    words = list(text)
    lines, line = [], ""
    for ch in words:
        test = line + ch
        if draw.textbbox((0, 0), test, font=f)[2] > max_width and line:
            lines.append(line)
            line = ch
        else:
            line = test
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textbbox((0, 0), last + "…", font=f)[2] > max_width:
            last = last[:-1]
        lines[-1] = last + "…"
    return lines

def generate(job):
    OUT.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (1080, 1080), "#F2F8FF")
    d = ImageDraw.Draw(im)
    navy, blue, muted = "#132B4E", "#1264C8", "#52647B"
    d.rounded_rectangle((35, 35, 1045, 175), radius=26, fill=navy)
    d.text((75, 75), "CAREERPICK  |  채용정보", font=font(46), fill="white")
    d.text((65, 220), clean(job.get("org"))[:38], font=font(40), fill=blue)
    title = clean(job.get("title"))
    lines = wrap(d, title, font(65), 950, 2)
    y = 300
    for line in lines:
        d.text((65, y), line, font=font(65), fill=navy)
        y += 90
    d.rounded_rectangle((45, 610, 1035, 925), radius=30, fill="white")
    count = job.get("count")
    count_text = f"{count}명" if isinstance(count, int) and not isinstance(count, bool) and count >= 0 else "공고 확인"
    fields = [
        ("채용인원", count_text),
        ("접수마감", clean(job.get("due"))),
        ("고용형태", clean(job.get("employment"))),
    ]
    for i, (label, value) in enumerate(fields):
        yy = 642 + i * 92
        d.text((80, yy), label, font=font(34), fill=muted)
        d.text((330, yy-5), clean(value)[:23], font=font(43), fill=navy)
    d.rounded_rectangle((45, 952, 1035, 1040), radius=20, fill=blue)
    footer = "자세한 채용공고: 커리어픽 프로필링크"
    d.text((80, 971), footer, font=font(37), fill="white")
    identifier = re.sub(r"[^A-Za-z0-9_-]", "_", str(job.get("id", "job")))[:70]
    path = OUT / (identifier + ".jpg")
    im.save(path, "JPEG", quality=92, optimize=True)
    if path.stat().st_size < 10_000:
        raise RuntimeError("Generated image is unexpectedly small")
    with Image.open(path) as check:
        check.verify()
    with Image.open(path) as check:
        if check.format != "JPEG" or check.size != (1080, 1080):
            raise RuntimeError("Generated image format or dimensions invalid")
    return path

if __name__ == "__main__":
    print(generate(json.loads(sys.argv[1])))
