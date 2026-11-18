# CareerPick card-news isolated integration (2026-11-14)

This feature is **opt-in and offline-first**. It does not modify the existing website, collector, Threads scheduler, push delivery, or GitHub Actions.

## Safety contract
- Never auto-publish. Manual review and explicit approval required.
- Do not insert unverified salaries, employment benefits, dates, or qualifications.
- Input must be a manually verified JSON document with provenance.
- Store outputs under a local directory, not the live website.
- Do not read or print tokens or environment secrets.
- Keep original source hash and exact cited text for each claimed fact.
- Reject incomplete required fields and expired deadlines.
- Existing CareerPick operations remain unchanged.

## Setup
1. Download the separately tested `careerpick_cardnews_final_kit.zip` package from the conversation.
2. Install Python dependencies in an isolated virtual environment according to its README.
3. Prepare a verified JSON input from the official vacancy and attachments.
4. Run the package's generator and validator locally.
5. Review each generated image and compare every number against the official notice.
6. Upload only approved images manually. Automatic publishing is not enabled.

## Release gates
- At least one **real official notice** with source URL and captured revision/date.
- Extraction compared against the original attachments.
- 3–8 card PNGs checked for readable Korean text and layout.
- Captions checked against platform-specific CTA and URL policy.
- Archive re-opened and checksums verified.
- Duplicate protection and idempotent retry demonstrated.
- No impact on the existing website and Threads flows.
- Publishing integration requires separate sandbox validation and explicit approval.

Status: documentation-only integration branch. No live publishing, automated extraction, or production deployment is claimed.
