import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from scripts import create_thumbnail as cards


class ThreadsThumbnailTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.out_patch = patch.object(cards, "OUT", self.directory)
        self.out_patch.start()
        self.addCleanup(self.out_patch.stop)
        self.job = {
            "id": "a123",
            "org": "강원특별자치도 지역산업진흥원 인재채용지원센터",
            "title": "2026년 하반기 정보보안 운영 및 공공데이터 품질관리 전문인력 공개채용",
            "count": 12,
            "employment": "기간제 근로자(계약기간 1년, 정규직 전환 없음)",
            "location": "강원특별자치도 춘천시 및 인제군 사업장",
            "due": "2026-11-23",
            "deadline_label": "2026년 11월 23일 18:00 (한국시간)",
        }

    def capture_render(self, job):
        drawn = []
        original = ImageDraw.ImageDraw.text

        def capture(draw, position, text, *args, **kwargs):
            bounds = draw.textbbox(position, text, font=kwargs["font"])
            drawn.append((text, bounds))
            return original(draw, position, text, *args, **kwargs)

        with patch.object(ImageDraw.ImageDraw, "text", capture):
            path = cards.generate(job)
        return path, drawn

    def test_full_long_korean_facts_and_exact_cta_fit_in_card(self):
        path, drawn = self.capture_render(self.job)
        rendered = "".join(text for text, _ in drawn).replace(" ", "")
        for key in ("org", "title", "employment", "location", "deadline_label"):
            with self.subTest(key=key):
                self.assertIn(self.job[key].replace(" ", ""), rendered)
        self.assertIn("12명", rendered)
        self.assertEqual(rendered.count(cards.CTA.replace(" ", "")), 1)
        self.assertTrue(rendered.endswith(cards.CTA.replace(" ", "")))
        self.assertNotIn("…", rendered)
        for _, (left, top, right, bottom) in drawn:
            self.assertGreaterEqual(left, 40)
            self.assertGreaterEqual(top, 38)
            self.assertLessEqual(right, 1040)
            self.assertLessEqual(bottom, 1042)
        metadata = cards.verify_thumbnail(path)
        self.assertTrue(metadata["valid"])
        self.assertEqual((metadata["width"], metadata["height"]), (1080, 1080))
        self.assertEqual(metadata["format"], "JPEG")
        self.assertGreater(metadata["file_size_bytes"], 10_000)
        self.assertLessEqual(metadata["file_size_bytes"], 8_000_000)

    def test_overlong_material_facts_fail_without_a_partial_image(self):
        for field in ("org", "title", "employment", "location", "deadline_label"):
            with self.subTest(field=field):
                job = {**self.job, "id": field, field: "필수조건을삭제하면안됩니다" * 35}
                with self.assertRaises(cards.ThumbnailLayoutError):
                    cards.generate(job)
                self.assertFalse((self.directory / f"{field}.jpg").exists())
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_unspecified_count_and_date_only_are_not_invented(self):
        job = {**self.job, "count": "00명", "deadline_label": None}
        _, drawn = self.capture_render(job)
        rendered = "".join(text for text, _ in drawn)
        self.assertIn("00명", rendered)
        self.assertIn("2026-11-23", rendered)
        self.assertNotIn("18:00", rendered)
        self.assertNotIn("23:59", rendered)

    def test_legacy_minimal_job_returns_verified_path(self):
        job = {"id": "legacy", "org": "테스트기관", "title": "채용", "count": 16, "due": "2026-11-23"}
        path = cards.generate(job)
        self.assertIsInstance(path, Path)
        self.assertEqual(path.name, "legacy.jpg")
        self.assertTrue(cards.verify_thumbnail(path)["valid"])

    def test_failed_verification_keeps_previous_file_and_removes_temporary(self):
        existing = self.directory / "a123.jpg"
        existing.write_bytes(b"previous image")
        with patch.object(cards, "verify_thumbnail", side_effect=cards.ThumbnailValidationError("decode failed")):
            with self.assertRaises(cards.ThumbnailValidationError):
                cards.generate(self.job)
        self.assertEqual(existing.read_bytes(), b"previous image")
        self.assertEqual(list(self.directory.iterdir()), [existing])

    def test_wrong_type_dimensions_and_color_mode_are_rejected(self):
        cases = [
            ("PNG", "RGB", (1080, 1080)),
            ("JPEG", "RGB", (1079, 1080)),
            ("JPEG", "CMYK", (1080, 1080)),
        ]
        for index, (image_format, mode, size) in enumerate(cases):
            with self.subTest(image_format=image_format, mode=mode, size=size):
                path = self.directory / f"invalid-{index}.jpg"
                Image.new(mode, size).save(path, image_format)
                with self.assertRaises(cards.ThumbnailValidationError):
                    cards.verify_thumbnail(path)

    def test_truncated_pixel_data_is_rejected_even_with_jpeg_header(self):
        path = cards.generate(self.job)
        content = path.read_bytes()
        path.write_bytes(content[:len(content) // 2])
        with self.assertRaises(cards.ThumbnailValidationError):
            cards.verify_thumbnail(path)

    def test_oversized_and_empty_files_are_rejected(self):
        path = self.directory / "invalid.jpg"
        path.write_bytes(b"")
        with self.assertRaises(cards.ThumbnailValidationError):
            cards.verify_thumbnail(path)
        with path.open("wb") as handle:
            handle.truncate(cards.MAX_IMAGE_BYTES + 1)
        with self.assertRaises(cards.ThumbnailValidationError):
            cards.verify_thumbnail(path)

    def test_unsupported_or_invisible_text_fails_instead_of_missing_glyphs(self):
        for suffix in ("\U0010ffff", "\u202e"):
            with self.subTest(suffix=repr(suffix)):
                with self.assertRaises(cards.ThumbnailLayoutError):
                    cards.generate({**self.job, "title": self.job["title"] + suffix})
        self.assertEqual(list(self.directory.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
