"""Read-only binding of a reviewed 360px preview to final publishable bytes.

The writer must open the saved preview before attesting a passed review. This
module cannot perform that visual judgment; it checks that publishing uses the
same image, facts and preview as the attestation. It never renders or writes.
"""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

COMPACT_LAYOUT_VERSION = "careerpick-single-main-card-v2"


def _fail(code):
    from scripts.threads_writer_queue import QueueValidationError
    raise QueueValidationError("CARD_" + code)


def card_facts_sha256(job):
    """Canonical hash of the complete validated rendering input, including restriction."""
    if not isinstance(job, dict):
        _fail("FACTS_SCHEMA")
    try:
        data = json.dumps(job, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        _fail("FACTS_SCHEMA")
    return hashlib.sha256(data).hexdigest()


def _moment(value, code):
    try:
        value = value if isinstance(value, datetime) else datetime.fromisoformat(value)
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError
        return value
    except (TypeError, ValueError, OverflowError):
        _fail(code)


def _asset(root, supplied, expected):
    if not isinstance(supplied, str) or supplied != expected:
        _fail("ASSET_PATH")
    candidate = root / supplied
    if (root / "threads-images").is_symlink() or candidate.is_symlink():
        _fail("ASSET_SYMLINK")
    try:
        actual = candidate.resolve(strict=True)
        actual.relative_to(root)
    except (OSError, ValueError):
        _fail("ASSET_MISSING_OR_OUTSIDE_ROOT")
    if not actual.is_file():
        _fail("ASSET_NOT_FILE")
    return actual


def _digest(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def verify_reviewed_card(job, review, root, now, verify_pixels=True):
    """Return verified asset metadata, or reject without changing any file.

    ``review`` is the writer's review dictionary, with v5.card_visual_review.
    Required paths are threads-images/<id>.jpg and <id>-360.png. The saved PNG
    must be the RGB LANCZOS 360x360 downsample of that exact final JPEG.
    ``verify_pixels=False`` is the stdlib-only reservation check. It still
    verifies every attestation/path/hash/fact/time binding but must be followed
    by the default full check before sending the image.
    """
    if not isinstance(job, dict) or not isinstance(review, dict):
        _fail("REVIEW_SCHEMA")
    meta = review.get("v5", {})
    proof = meta.get("card_visual_review") if isinstance(meta, dict) else None
    if not isinstance(proof, dict) or proof.get("status") != "passed":
        _fail("VISUAL_REVIEW_REQUIRED")
    if type(proof.get("reviewed_width")) is not int or proof["reviewed_width"] != 360:
        _fail("REVIEW_WIDTH")
    reviewed = _moment(proof.get("reviewed_at"), "REVIEW_TIME")
    current = _moment(now, "CURRENT_TIME")
    if reviewed > current:
        _fail("FUTURE_REVIEW")
    if proof.get("layout_version") != COMPACT_LAYOUT_VERSION:
        _fail("LAYOUT_VERSION")
    facts_sha256 = card_facts_sha256(job)
    if proof.get("facts_sha256") != facts_sha256:
        _fail("FACTS_CHANGED")
    identifier = job.get("id")
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,70}", identifier):
        _fail("NOTICE_ID")
    root = Path(root).resolve()
    image_path = _asset(root, proof.get("asset_path"), f"threads-images/{identifier}.jpg")
    preview_path = _asset(root, proof.get("preview_asset_path"), f"threads-images/{identifier}-360.png")
    if not _digest(proof.get("sha256")) or not _digest(proof.get("preview_sha256")):
        _fail("HASH_SCHEMA")
    image_size = image_path.stat().st_size
    if not 0 < image_size <= 8_000_000:
        _fail("JPEG_SIZE")
    image_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
    if image_sha256 != proof["sha256"]:
        _fail("IMAGE_CHANGED")
    if not 0 < preview_path.stat().st_size <= 2_000_000:
        _fail("PREVIEW_SIZE")
    preview_sha256 = hashlib.sha256(preview_path.read_bytes()).hexdigest()
    if preview_sha256 != proof["preview_sha256"]:
        _fail("PREVIEW_CHANGED")
    quality = {"file_size_bytes":image_size,
               "pixel_verification":"not_performed"}
    if verify_pixels:
        # Deferred imports keep the pre-reservation check usable before the
        # image-only workflow installs Pillow/fonts. Never downgrade a full
        # publish check automatically when its dependencies are unavailable.
        try:
            from PIL import Image
            from scripts.create_thumbnail import COMPACT_LAYOUT_VERSION as renderer_version, verify_thumbnail
        except ImportError:
            _fail("PIXEL_DEPENDENCY_UNAVAILABLE")
        if renderer_version != COMPACT_LAYOUT_VERSION:
            _fail("RENDERER_VERSION_MISMATCH")
        try:
            quality = {**verify_thumbnail(image_path),"pixel_verification":"passed"}
        except (ValueError, OSError):
            _fail("JPEG_INVALID")
        try:
            with Image.open(preview_path) as preview:
                if (preview.format != "PNG" or preview.size != (360, 360)
                        or preview.mode != "RGB" or getattr(preview, "n_frames", 1) != 1):
                    _fail("PREVIEW_FORMAT")
                preview.load()
                with Image.open(image_path) as source:
                    source.load()
                    expected = source.resize((360, 360), Image.Resampling.LANCZOS)
                    if preview.tobytes() != expected.tobytes():
                        _fail("PREVIEW_NOT_FINAL_IMAGE")
        except (OSError, SyntaxError):
            _fail("PREVIEW_INVALID")
    return {
        **quality,
        "layout_version": COMPACT_LAYOUT_VERSION,
        "asset_path": proof["asset_path"], "local_path": str(image_path),
        "sha256": image_sha256, "facts_sha256": facts_sha256,
        "preview_asset_path": proof["preview_asset_path"],
        "preview_sha256": preview_sha256,
        "reviewed_width": 360, "reviewed_at": reviewed.isoformat(),
        "visual_review": "attestation_and_exact_assets_verified",
    }
