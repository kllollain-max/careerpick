"""Contracts that matter at the public card boundary, without publishing."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import ImageDraw

from scripts import create_thumbnail as cards


class CompactCardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.job = {
            "org": "충청남도개발공사", "title": "기술6급 건축",
            "employment": "일반정규직", "count": 3,
            "deadline_label": "2026-11-12 18:00",
            "restriction": "충남 관련 응시요건 확인",
        }

    def draw(self, job):
        drawn = []
        original = ImageDraw.ImageDraw.text

        def capture(draw, position, text, *args, **kwargs):
            f = kwargs["font"]
            drawn.append({"text": text, "size": f.size,
                          "bounds": draw.textbbox(position, text, font=f)})
            return original(draw, position, text, *args, **kwargs)

        path = self.directory / "card.jpg"
        with patch.object(ImageDraw.ImageDraw, "text", capture):
            result = cards.generate_compact_card(job, path)
        return path, result, drawn

    def test_fact_hierarchy_without_banner_or_truncation(self):
        path, meta, drawn = self.draw(self.job)
        visible = "".join(x["text"] for x in drawn).replace(" ", "")
        for field in ("org", "title", "employment", "restriction"):
            self.assertIn(self.job[field].replace(" ", ""), visible)
        self.assertIn("3명", visible)
        self.assertIn("11월12일18:00", visible)
        self.assertNotIn(cards.CTA.replace(" ", ""), visible)
        self.assertNotIn("프로필", visible)
        self.assertNotIn("…", visible)
        self.assertEqual(meta["rendered_fields"]["deadline_label"], "11월 12일 18:00")
        self.assertTrue(cards.verify_thumbnail(path)["valid"])
        self.assertEqual(meta["human_visual_review"], "required")

        title_size = next(x["size"] for x in drawn if x["text"] == self.job["title"])
        employment_size = next(x["size"] for x in drawn if "3명" in x["text"])
        org_size = next(x["size"] for x in drawn if x["text"] == self.job["org"])
        brand_size = next(x["size"] for x in drawn if x["text"] == "커리어픽")
        self.assertGreater(title_size, org_size)
        self.assertGreater(employment_size, org_size)
        self.assertLess(brand_size, org_size)
        for row in drawn:
            left, top, right, bottom = row["bounds"]
            self.assertGreaterEqual(left, 48)
            self.assertGreaterEqual(top, 45)
            self.assertLessEqual(right, 1032)
            self.assertLessEqual(bottom, 1032)

    def test_optional_restriction_absence_does_not_invent_a_condition(self):
        job = {k:v for k,v in self.job.items() if k != "restriction"}
        _, meta, drawn = self.draw(job)
        self.assertEqual(meta["rendered_fields"]["restriction"], "")
        self.assertFalse(any("응시요건" in x["text"] for x in drawn))

    def test_invalid_or_overlong_fields_leave_existing_image_intact(self):
        path = self.directory / "card.jpg"
        original = b"prior verified image"
        path.write_bytes(original)
        for key in ("title", "org", "employment", "restriction"):
            with self.subTest(key=key):
                with self.assertRaises(cards.ThumbnailLayoutError):
                    cards.generate_compact_card({**self.job, key:"삭제하면안되는필수조건" * 30}, path)
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(list(self.directory.iterdir()), [path])

    def test_exact_clock_precision_and_unknown_count_are_preserved(self):
        cases = [
            ("2026-11-12", "11월 12일"),
            ("2026-11-12 09:05", "11월 12일 09:05"),
            ("2026-11-12 09:05:30", "11월 12일 09:05:30"),
        ]
        for raw, visible in cases:
            with self.subTest(raw=raw):
                _, meta, _ = self.draw({**self.job, "deadline_label":raw, "count":"00명"})
                self.assertEqual(meta["rendered_fields"]["deadline_label"], visible)
                self.assertEqual(meta["rendered_fields"]["count"], "00명")
        _, meta, _ = self.draw({**self.job, "count":None})
        self.assertEqual(meta["rendered_fields"]["count"], "인원 공고 확인")

    def test_link_hashtag_and_glyph_fail_before_writing(self):
        for value in ("공고 example.com", "공고 www.example.kr", "공고 hxxps://example", "공고 #채용", "공고 \U0010ffff", "공고\u202e"):
            with self.subTest(value=value):
                with self.assertRaises(cards.ThumbnailLayoutError):
                    cards.generate_compact_card({**self.job, "title":value}, self.directory / "bad.jpg")
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_invalid_deadline_does_not_become_an_apparently_valid_card(self):
        with self.assertRaises(cards.ThumbnailLayoutError):
            cards.generate_compact_card({**self.job, "deadline_label":"2026-02-30 18:00"}, self.directory / "bad.jpg")
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_failed_jpeg_validation_keeps_previous_image(self):
        path = self.directory / "card.jpg"
        path.write_bytes(b"prior verified image")
        with patch.object(cards, "verify_thumbnail", side_effect=cards.ThumbnailValidationError("decode failed")):
            with self.assertRaises(cards.ThumbnailValidationError):
                cards.generate_compact_card(self.job, path)
        self.assertEqual(path.read_bytes(), b"prior verified image")
        self.assertEqual(list(self.directory.iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
