import copy
import hashlib
import tempfile
import unittest
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from scripts.create_thumbnail import COMPACT_LAYOUT_VERSION, generate_compact_card
from scripts.threads_card_review import card_facts_sha256, verify_reviewed_card
from scripts.threads_writer_queue import QueueValidationError


class ReviewedCardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.job = {"id":"a123", "org":"검증기관", "title":"건축직", "count":3,
                    "employment":"정규직", "deadline_label":"2026-11-16 17:30:00",
                    "restriction":"면허 조건 확인"}
        self.image = self.root / "threads-images/a123.jpg"
        self.preview = self.root / "threads-images/a123-360.png"
        generate_compact_card(self.job, self.image)
        with Image.open(self.image) as im:
            im.resize((360,360),Image.Resampling.LANCZOS).save(self.preview)
        self.proof = {
            "status":"passed", "reviewed_width":360, "reviewed_at":"2026-11-11T18:00:00+09:00",
            "layout_version":COMPACT_LAYOUT_VERSION, "facts_sha256":card_facts_sha256(self.job),
            "asset_path":"threads-images/a123.jpg", "preview_asset_path":"threads-images/a123-360.png",
            "sha256":hashlib.sha256(self.image.read_bytes()).hexdigest(),
            "preview_sha256":hashlib.sha256(self.preview.read_bytes()).hexdigest(),
        }
        self.now = "2026-11-11T18:01:00+09:00"

    def verify(self, job=None, proof=None):
        return verify_reviewed_card(job or self.job, {"v5":{"card_visual_review":proof or self.proof}}, self.root, self.now)

    def test_reviewed_final_bytes_pass_without_writing_or_rendering(self):
        before = {p.name:(p.stat().st_mtime_ns,p.read_bytes()) for p in self.image.parent.iterdir()}
        with patch("scripts.create_thumbnail.generate_compact_card", side_effect=AssertionError("must not regenerate")):
            quality = self.verify()
        after = {p.name:(p.stat().st_mtime_ns,p.read_bytes()) for p in self.image.parent.iterdir()}
        self.assertEqual(before,after)
        self.assertEqual(quality["sha256"],self.proof["sha256"])
        self.assertEqual(quality["reviewed_width"],360)
        self.assertEqual(card_facts_sha256(self.job),card_facts_sha256(dict(reversed(list(self.job.items())))))

    def test_reservation_checks_import_and_run_without_pillow(self):
        import builtins
        real_import = builtins.__import__
        def without_pillow(name,*args,**kwargs):
            if name == "PIL" or name.startswith("PIL."):
                raise ImportError("Pillow not yet installed")
            return real_import(name,*args,**kwargs)
        with patch.object(builtins,"__import__",side_effect=without_pillow):
            quality=verify_reviewed_card(self.job,{"v5":{"card_visual_review":self.proof}},self.root,self.now,verify_pixels=False)
            self.assertEqual(quality["pixel_verification"],"not_performed")
            self.assertNotIn("valid",quality)
            with self.assertRaisesRegex(QueueValidationError,"PIXEL_DEPENDENCY_UNAVAILABLE"):
                self.verify()
        # A clean Python process without site-packages can import the helper.
        result=subprocess.run([sys.executable,"-S","-c","import scripts.threads_card_review"],
                              cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_changed_image_or_facts_cannot_reuse_review(self):
        with self.assertRaisesRegex(QueueValidationError,"FACTS_CHANGED"):
            self.verify(job={**self.job,"count":4})
        with self.assertRaisesRegex(QueueValidationError,"FACTS_CHANGED"):
            self.verify(job={**self.job,"restriction":"거주 조건 확인"})
        with Image.open(self.image) as original: altered=original.copy()
        altered.putpixel((500,500),(250,0,0));altered.save(self.image,"JPEG",quality=95)
        with self.assertRaisesRegex(QueueValidationError,"IMAGE_CHANGED"):
            self.verify()

    def test_proof_requires_aware_non_future_time_and_exact_policy(self):
        cases = [
            ("reviewed_at","2026-11-11T18:00:00","REVIEW_TIME"),
            ("reviewed_at","2026-11-11T18:02:00+09:00","FUTURE_REVIEW"),
            ("status","planned","VISUAL_REVIEW_REQUIRED"),
            ("reviewed_width",1080,"REVIEW_WIDTH"),
            ("layout_version","old-layout","LAYOUT_VERSION"),
        ]
        for field,value,error in cases:
            with self.subTest(field=field,value=value),self.assertRaisesRegex(QueueValidationError,error):
                self.verify(proof={**self.proof,field:value})

    def test_asset_paths_cannot_escape_or_switch_notice(self):
        for path in ("../a123.jpg","threads-images/a124.jpg","threads-images/../a123.jpg","/tmp/a123.jpg","threads-images\\a123.jpg"):
            with self.subTest(path=path),self.assertRaisesRegex(QueueValidationError,"ASSET_PATH"):
                self.verify(proof={**self.proof,"asset_path":path})
        original = self.root / "original.jpg"
        self.image.rename(original);self.image.symlink_to(original)
        with self.assertRaisesRegex(QueueValidationError,"ASSET_SYMLINK"):
            self.verify()

    def test_missing_or_mismatched_preview_is_rejected(self):
        with Image.open(self.preview) as original: altered=original.copy()
        altered.putpixel((10,10),(0,0,0));altered.save(self.preview)
        with self.assertRaisesRegex(QueueValidationError,"PREVIEW_CHANGED"):
            self.verify()
        # Even a changed preview hash cannot pair an unrelated visual with the final JPEG.
        proof={**self.proof,"preview_sha256":hashlib.sha256(self.preview.read_bytes()).hexdigest()}
        with self.assertRaisesRegex(QueueValidationError,"PREVIEW_NOT_FINAL_IMAGE"):
            self.verify(proof=proof)
        self.preview.unlink()
        with self.assertRaisesRegex(QueueValidationError,"ASSET_MISSING"):
            self.verify()

    def test_numeric_dimension_claim_does_not_replace_actual_360_preview(self):
        Image.new("RGB",(720,720),"white").save(self.preview)
        proof={**self.proof,"preview_sha256":hashlib.sha256(self.preview.read_bytes()).hexdigest()}
        with self.assertRaisesRegex(QueueValidationError,"PREVIEW_FORMAT"):
            self.verify(proof=proof)


if __name__ == "__main__":
    unittest.main()
