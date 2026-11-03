# CareerPick

Restored from `CareerPick_kllollain_max_restore_20261101.zip`; original public snapshot commit `716c86da48ae2e852f75655af746d3ac8e7c494b`.

Repository: `kllollain-max/careerpick`, originally created as a private repository on 2026-11-03.
Live site: [CareerPick](https://kllollain-max.github.io/careerpick/).

## Initial release status

On 2026-11-03 the owner approved making this repository public, merging PR #1 and running one manual GitHub Pages deployment for free operation. PR #1 was merged at 06:49:34 UTC in `643bd425621dc1ca5fcb479aee09733a346049ea`. The reviewed manual workflow was added to main in `d4d9681a935aa899a5605e5ae1ed7c803c795966`. The repository is now public and the approved manual Pages deployment succeeded.

The live deployment uses the approved source SHA below. Later audit/documentation commits on main do not change the published site automatically.

| Release record | Actual result |
|---|---|
| Recorded at (KST) | `2026-11-03 16:15:32 KST` |
| Repository visibility | `public` |
| Main commit at deployment | `13b5e59280411940fdd7cb73617aa397a2ac9a44` |
| Pages configuration | `GitHub Actions; HTTPS site enabled` |
| Approved deployment source SHA | `bee342c7c1db94e44172b47b78443540c7a34147` |
| Deployment run | `https://github.com/kllollain-max/careerpick/actions/runs/41593785022` |
| Deployment result | `success — 2026-11-03 16:04:08 KST` |
| Live root, direct detail, assets and browser storage | `PASS: root rendering; 한국잡월드 search returned 2 results; saved notice persisted across detail navigation and root return; test save removed (0 remaining); /careerpick/jobs/a306130.html direct open and refresh; sampled assets/data HTTP 200.` |

Scheduled collection, automatic production-data updates and production integration of the new GOJOBS/MPM APIs remain on hold.

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

Published ALIO snapshot: 610 unique IDs, collected 2026-11-03 12:32:01 KST. This includes 520 preserved cards plus 90 new cards. Date-expired retained notices are not active vacancies. Archived and newly generated detail pages are a separate population. Date-based deadline states update at build/runtime; official corrections and early closures require live collection and source checks. Date-only deadlines remain uncertain on the closing day. Every notice's latest reception status has NOT been independently verified.

Search, filters, matched conditions, saved notices and application tracking reuse the original code. Browser storage is local to the device/domain; there is no recovered account sign-in or server synchronization. Old-domain local storage cannot migrate automatically; original JSON import/export remains available.

## Collection

`alio.py` is reused from the emergency delivery snapshot; `scripts/collect_alio.py` stages collection and validates/merges by official ID, preserving archived notices and details. It has no history, qnet, social publishing or deployment side effects.

Required Secret: `ALIO_KEY` for the official ALIO OpenData service. On 2026-11-03 the signed-in official Swagger UI verified POST/query endpoints `https://opendata.alio.go.kr/new/v1/recruit/list.do` and `detail.do`, required `serviceKey`, detail `sn`, and JSON envelopes. See `docs/ALIO_NEW_CONTRACT_20261103.md`. The legacy data.go.kr key is not interchangeable.

`scripts/verify_alio_live.py` checks list and one independent detail identity, then collects in an isolated staging directory. It leaves repository snapshots untouched and produces Actions candidate artifacts plus a sanitized report. A failed check does not prove bad credentials or missing approval unless an official numeric response identifies it.

The ALIO live-check workflow has read-only contents permission and runs on pushes affecting named check files on the restoration branch only. There is no schedule or deployment. Existing manual static verification remains available. The reviewed Pages workflow is active at `.github/workflows/deploy-pages.yml` and accepts manual dispatch only, with an exact `approved_sha`. Production persistence and scheduling remain on hold.

## Deployment and operating scope

The owner approved the initial public release. PR #1 is merged and the website is published using GitHub Pages from GitHub Actions. The active workflow `.github/workflows/deploy-pages.yml` runs only on manual dispatch, requires `approval=DEPLOY_CAREERPICK` and a reviewed 40-character `approved_sha`, verifies the checked-out SHA, and publishes only the generated `dist/`.

Scheduled collection, automatic production-data updates and GOJOBS/MPM production integration remain on hold. The manual candidate collection proposal stays in `review-workflows/collect-alio.yml.disabled`. Blog, Threads and other repository schedules are outside this release.

Rollback uses a previously verified source commit through the manual deployment workflow while preserving JSON snapshots and browser data. New certificate/recommendation/advertising functionality is not implemented; archived pages remain for compatibility.

## Candidate integration validation

The verified candidate pair is now applied to the recovery branch. All 520 previous cards are unchanged; all 90 new IDs have matching detail records and generated detail pages. Successful validation of code HEAD 26d8c36200f62f71b7c952043b508e805467e716: https://github.com/kllollain-max/careerpick/actions/runs/41573700536 . Build: 1,288 files, 30,141 HTML links, missing links 0; detail tests 27 and homepage tests 48 passed. Search/detail checks at 320/390/1440px passed with Korean fonts. This remains the predeployment validation record. The current release result is recorded above; scheduled collection remains disabled.

## Release evidence

[Deployment run](https://github.com/kllollain-max/careerpick/actions/runs/41593785022) succeeded with 610 ALIO rows, 1,288 output files and 30,141 checked HTML links with no missing local links. Public HTTP checks confirmed that both data JSON files exactly match their retained SHA256 hashes. See [release evidence](docs/evidence/public-release-20261103.json).

[History audit](https://github.com/kllollain-max/careerpick/actions/runs/41593953112) passed: 36 reachable commits, 1,332 blobs, all four registered credentials checked, zero unresolved findings. Three exact historical mock-test fixtures were reviewed and recorded separately. This targets registered credentials and high-signal token/private-key patterns; it is not a guarantee about every unknown secret type.
