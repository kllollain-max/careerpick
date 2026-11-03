#!/usr/bin/env python3
"""Offline regression: later-page API failure must not truncate ALIO snapshots."""
import tempfile
from pathlib import Path
from unittest.mock import patch
import alio


def main():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "alio.json"
        detail = Path(tmp) / "alio-detail.json"
        original = '{"updated":"prior","posts":[{"id":"a1"}]}'
        out.write_text(original, encoding="utf-8")
        detail.write_text('{"a1":{}}', encoding="utf-8")
        calls = []

        def fake_call(key, page):
            calls.append(page)
            if page == 1:
                return {"totalCount": 200, "result": [{"id": str(i)} for i in range(alio.PER_PAGE)]}
            raise TimeoutError("later page failed")

        with patch.object(alio, "OUT", out), patch.object(alio, "DETAIL", detail), patch.object(alio, "call", fake_call), patch.dict(alio.os.environ, {"ALIO_KEY": "offline-test-key"}):
            result = alio.main()
        assert result is None
        assert calls == [1, 2], calls
        assert out.read_text(encoding="utf-8") == original
        assert detail.read_text(encoding="utf-8") == '{"a1":{}}'
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "alio.json"
        detail = Path(tmp) / "alio-detail.json"
        out.write_text('{"posts":[{"id":"a1"}]}', encoding="utf-8")
        detail.write_text('{"a1":{}}', encoding="utf-8")
        with patch.object(alio, "OUT", out), patch.object(alio, "DETAIL", detail), patch.object(alio, "MAX_PAGES", 1), patch.object(alio, "call", lambda key, page: {"totalCount": 250, "result": [{"id": str(i)} for i in range(alio.PER_PAGE)]}), patch.dict(alio.os.environ, {"ALIO_KEY": "offline-test-key"}):
            result = alio.main()
        assert result is None
        assert out.read_text(encoding="utf-8") == '{"posts":[{"id":"a1"}]}'
        assert detail.read_text(encoding="utf-8") == '{"a1":{}}'
    print("ALIO partial fetch guard: PASS")


if __name__ == "__main__":
    main()
