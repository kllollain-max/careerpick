# CareerPick: safe operating, search, and ad-readiness review

This is an **offline review-only** proposal. It does not modify public pages, ad scripts, publication, job data, or sending permissions. Approval is required before merging/deploying.

## 1. Operating reliability

- Owner elected to pause the push feature: `.github/workflows/targeted-push.yml` must have **manual workflow_dispatch only**, not `workflow_run` or `schedule`. Keep existing private ledger, circuit breaker, OneSignal credentials, and historical subscription records intact. No implicit resume or historical replay.
- Continue the existing 3-hour recruitment collection, existing safety guards, Threads publication, and public-search audit. No new cron or external API calls.
- Before future push resumption: require the current app subscriber audit, verified consent for every intended recipient, no pending/reserved/uncertain entries, exact control SHA, then separate owner approval.

## 2. Editorial traffic growth (without invented search volume)

- The new `scripts/priority_candidate_audit.py` reads only existing validated ALIO source fields and writes an offline JSON report under `review-only/`.
- It favors clearly categorized regular employment and source-reported recruitment headcount, and excludes expired, unknown-deadline, duplicated IDs, or nonofficial links.
- `triage_score` is an **internal editorial review score**, not Naver search volume, user popularity, applicant count, verified headcount, or current application availability. Treat unknown hiring counts as unknown, never zero.
- An editor must cross-check the source job notice, category, number of openings, registration period, and official link before any publication or Threads promotion. Data source coverage is bounded; do not infer nationwide completeness.
- Use genuine Google Search Console or Naver Search Advisor impression/click/CTR data when connected; otherwise report `not_connected`, not invented metrics.

## 3. AdSense and SEO readiness (no monetization activation)

Existing audits already cover canonical URLs, sitemap/indexability, structured data, missing policy links, and a fail-closed advertising inventory. Reuse them; do not duplicate new crawlers or inject ad tags.
- Review duplicate content/title warnings, thin/expired vacancy pages, guide citations, mobile readability, and official-source freshness before seeking monetization approval.
- Ensure About, Contact, Privacy and editorial/attribution disclosures are understandable and reachable. A passing offline CI **does not guarantee** Google indexing, AdSense approval, ranking, or advertiser acceptance.
- Ads must remain disabled until separate owner approval, privacy/legal review and any consent duties are addressed.
- Deliverable: review-only candidate report and CI evidence; proposed site UI/SEO changes require a separate PR and approval.
