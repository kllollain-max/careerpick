#!/usr/bin/env python3
"""Read-only browser verification of the exact CareerPick a307061 profile, no publication."""
import asyncio
import json
import pathlib
from datetime import datetime, timezone

from playwright.async_api import async_playwright

ROOT = pathlib.Path("official-reviewed-evidence/a307061")
ROOT.mkdir(parents=True, exist_ok=True)
PROFILE = "https://kllollain-max.github.io/careerpick/#job=a307061"
async def main():
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "url": PROFILE, "notice_id": "a307061", "verified": False,
              "read_only": True, "meta_posted": False, "queue_updated": False}
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
            response = await page.goto(PROFILE, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(6500)
            body = await page.locator("body").inner_text(timeout=10000)
            report["http_status"] = response.status if response else None
            report["title"] = await page.title()
            report["actual_url"] = page.url
            report["body_chars"] = len(body)
            report["contains_employer"] = "우체국금융개발원" in body
            report["contains_notice_or_title"] = "307061" in body or "2026년 10차" in body
            report["contains_recruitment_detail"] = ("우체국금융개발원" in body and
                ("공개채용" in body or "보험고객상담" in body))
            report["verified"] = all((report["http_status"] == 200,
                report["contains_employer"], report["contains_notice_or_title"],
                report["contains_recruitment_detail"]))
            report["visible_context"] = body[:5000]
            (ROOT / "profile-visible.txt").write_text(body, encoding="utf-8")
            await page.screenshot(path=str(ROOT / "careerpick-a307061-mobile.png"), full_page=True)
            await browser.close()
    except Exception as exc:
        report["error"] = type(exc).__name__ + ": " + str(exc)[:400]
    finally:
        (ROOT / "profile-receipt.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("PROFILE_A307061_RECEIPT=" + json.dumps(report, ensure_ascii=False)[:7000])
    if not report["verified"]:
        raise SystemExit("HOLD: exact public CareerPick job profile not visually verified")
if __name__ == "__main__":
    asyncio.run(main())
