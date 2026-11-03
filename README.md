# CareerPick restoration — approval pending

Restored from `CareerPick_kllollain_max_restore_20261101.zip`; original public snapshot commit `716c86da48ae2e852f75655af746d3ac8e7c494b`.

Target repository: `kllollain-max/careerpick` (private repository created 2026-11-03).
Target URL after approval: `https://kllollain-max.github.io/careerpick/`.

## Run locally

```sh
python3 scripts/build_public_site.py
python3 -m unittest discover -s tests -p 'test_*.py'
node --test tests/test_homepage_ux.cjs
python3 -m scripts.test_prune_expired_job_schema
python3 -m scripts.test_build_sitemap
python3 test_alio_partial_fetch.py
```

Serve `dist/` mounted under `/careerpick/`. The source files preserve the original root layout; the builder scopes output links, canonical URLs and PWA to the project path. Deploy only `dist/`, never the repository root.

## Data and limitations

ALIO review branch: 610 unique IDs, collected 2026-11-03 12:32:01 KST. This includes 520 preserved cards plus 90 new cards. Date-expired retained notices are not active vacancies. Archived and newly generated detail pages are a separate population. Date-based deadline states update at build/runtime; official corrections and early closures require live collection and source checks. Date-only deadlines remain uncertain on the closing day. Every notice's latest reception status has NOT been independently verified.

Search, filters, matched conditions, saved notices and application tracking reuse the original code. Browser storage is local to the device/domain; there is no recovered account sign-in or server synchronization. Old-domain local storage cannot migrate automatically; original JSON import/export remains available.

## Collection

`alio.py` is reused from the emergency delivery snapshot; `scripts/collect_alio.py` stages collection and validates/merges by official ID, preserving archived notices and details. It has no history, qnet, social publishing or deployment side effects.

Required Secret: `ALIO_KEY` for the official ALIO OpenData service. On 2026-11-03 the signed-in official Swagger UI verified POST/query endpoints `https://opendata.alio.go.kr/new/v1/recruit/list.do` and `detail.do`, required `serviceKey`, detail `sn`, and JSON envelopes. See `docs/ALIO_NEW_CONTRACT_20261103.md`. The legacy data.go.kr key is not interchangeable.

`scripts/verify_alio_live.py` checks list and one independent detail identity, then collects in an isolated staging directory. It leaves repository snapshots untouched and produces private Actions candidate artifacts plus a sanitized report. A failed check does not prove bad credentials or missing approval unless an official numeric response identifies it.

The ALIO live-check workflow has read-only contents permission and runs on pushes affecting named check files on the restoration branch only. There is no schedule or deployment. Existing manual static verification remains available. Pages proposals remain disabled. Production persistence and scheduling require separate approval.

## Approval and deployment

1. Create a **private** `kllollain-max/careerpick` repository with an initial README and make it accessible through the existing GitHub connection. Repository created using the approved signed-in browser. GitHub connection confirms admin/push access.
2. Import this recovery branch, open a Draft PR; reuse successful tests unless merge integration changes inputs.
3. Review source/commit, data freshness, collection contract and secrets. Do not mix with automation-system PR #1/#5 or edit blog schedules.
4. Only after owner approval: merge, adjust visibility if the account's Pages plan requires it, enable GitHub Actions Pages source, activate the reviewed manual Pages workflow and run it once.
5. Verify live root, direct detail refresh, assets and browser storage. Only then report operational recovery.
6. Rollback: redeploy a previously verified static artifact/commit through the approved manual workflow; preserve JSON snapshots and browser data. For a first failed deployment, keep the last reviewed artifact and restore that exact artifact, or disable publication only with owner authorization.

New certificate/recommendation/advertising functionality is not implemented. Existing archived pages remain for compatibility. Ads, push and external blog automations are not enabled.

## Candidate integration validation

The verified candidate pair is now applied to the recovery branch. All 520 previous cards are unchanged; all 90 new IDs have matching detail records and generated detail pages. Successful validation of code HEAD 26d8c36200f62f71b7c952043b508e805467e716: https://github.com/kllollain-max/careerpick/actions/runs/41573700536 . Build: 1,288 files, 30,141 HTML links, missing links 0; detail tests 27 and homepage tests 48 passed. Search/detail checks at 320/390/1440px passed with Korean fonts. This is predeployment validation, not a live-site recovery claim. No schedule, main merge or Pages publication.
