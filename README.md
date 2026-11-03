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

ALIO snapshot: 520 unique IDs, 2026-10-30 23:43:53 KST. Detail archive: 794 static pages. These are different populations, not 794 current vacancies. Date-based deadline states update at build/runtime; official corrections and early closures require live collection and source checks. Date-only deadlines remain uncertain on the closing day. Every notice's latest reception status has NOT been independently verified.

Search, filters, matched conditions, saved notices and application tracking reuse the original code. Browser storage is local to the device/domain; there is no recovered account sign-in or server synchronization. Old-domain local storage cannot migrate automatically; original JSON import/export remains available.

## Collection

`alio.py` is reused from the emergency delivery snapshot; `scripts/collect_alio.py` stages collection and validates/merges by official ID, preserving archived notices and details. It has no history, qnet, social publishing or deployment side effects.

Required Secret: `ALIO_KEY` for the preserved data.go.kr endpoint (`https://apis.data.go.kr/1051000/recruitment/list`). The newer ALIO `/v1/recruit/list.do` and `/v1/recruit/detail.do` contracts are not substituted without authoritative contract verification. Key availability/approval and the live endpoint response remain unverified. Do not confuse these API products or reuse a key between them blindly.

The active verification workflow is manual only and has read permissions. Collector/deployer proposals live in `review-workflows/*.disabled`; they are inert. No scheduler exists in the active workflow. A production collection schedule still needs explicit approval, endpoint verification, a successful manual candidate run and reviewed data persistence wiring.

## Approval and deployment

1. Create a **private** `kllollain-max/careerpick` repository with an initial README and make it accessible through the existing GitHub connection. Repository created using the approved signed-in browser. GitHub connection confirms admin/push access.
2. Import this recovery branch, open a Draft PR; reuse successful tests unless merge integration changes inputs.
3. Review source/commit, data freshness, collection contract and secrets. Do not mix with automation-system PR #1/#5 or edit blog schedules.
4. Only after owner approval: merge, adjust visibility if the account's Pages plan requires it, enable GitHub Actions Pages source, activate the reviewed manual Pages workflow and run it once.
5. Verify live root, direct detail refresh, assets and browser storage. Only then report operational recovery.
6. Rollback: redeploy a previously verified static artifact/commit through the approved manual workflow; preserve JSON snapshots and browser data. For a first failed deployment, keep the last reviewed artifact and restore that exact artifact, or disable publication only with owner authorization.

New certificate/recommendation/advertising functionality is not implemented. Existing archived pages remain for compatibility. Ads, push and external blog automations are not enabled.
