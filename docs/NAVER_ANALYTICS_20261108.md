# CareerPick NAVER Analytics connection candidate

Prepared 2026-11-08 KST from main `cfbb3d26a5de23d0c2e322822fb0d8d323bc02a0`.
The owner supplied the NAVER site ID `1e121e3d2f09900` after registering CareerPick.
This branch is a review candidate. Its existence does not establish production
deployment or receipt of analytics data by NAVER.

## Resulting behavior

The public builder adds the local analytics script and stylesheet once to every
generated or preserved HTML page. The assets are included in `public-files.json`.
Direct NAVER snippets and advertising scripts remain rejected by the existing
public-build guard; the reviewed local loader is the explicit consent entrypoint.

The proposed visitor setting is off until the visitor chooses **허용**. This
matches the existing privacy notice's requirement to present the provider,
purpose and choice before enabling analytics. The provider, information types,
report retention reference and withdrawal behavior are described in privacy
section `#visit-analytics` for operator review with this change.

Only `https://kllollain-max.github.io/careerpick/` pages initialize this module.
The choice uses the site-specific local-storage key
`careerpick:naver-analytics-consent:v1`, with `granted` or `denied` values.
The sibling SupportPick project does not initialize CareerPick analytics.

After permission, the loader requests `https://wcs.pstatic.net/wcslog.js`, waits
for it to load, sets the supplied ID, then calls `wcs_do()` once per document.
No virtual pageviews or custom events for search, saved notices, forms or personal
notes are added. A provider pageview can include the current URL and referrer;
this is described in the notice rather than claiming that all URLs are anonymous.

Repeated initialization/clicks do not produce another pageview. Existing provider
scripts or an existing ID are not overwritten. Failure does not gate the site's
normal controls. A stored denial is honored on subsequent visits and in other
open tabs. Withdrawal reloads an already-connected document only after verifying
the stored setting. If storage is unavailable, the UI explains that a choice may
not persist and that an already-started connection requires closing the tab.

The local `sent` state means the SDK function returned; it is not a NAVER server
receipt or proof that a report was updated.

## Completed validation

- `python -m unittest discover -s tests -p 'test_naver_analytics_build.py' -v`:
  5 tests passed. Covers generated/archived-page insertion, repeat transformation,
  preserved bodies, missing/duplicate assets, incomplete HTML and direct-script
  rejection.
- `python -m unittest discover -s tests -p 'test_search_readiness.py' -v`:
  10 existing tests passed.
- `node --check naver-analytics.js`: passed.
- `node --test tests/naver_analytics_browser.cjs`: 8 tests passed with an available
  local Chromium executable supplied through `CP_ANALYTICS_CHROMIUM_EXECUTABLE`.
  All network requests were intercepted. The documents and NAVER SDK were local
  test fixtures, and no analytics data was sent to NAVER.

The browser checks cover default-off behavior, 320px layout, explicit permission,
repeat initialization, persistent choices, withdrawal, provider failure, blocked
storage, the sibling path, existing provider ID and cross-tab withdrawal.

The full repository build also passed in
[CI 42490471149](https://github.com/kllollain-max/careerpick/actions/runs/42490471149):
1,410 HTML pages, 37,876 checked HTML links, zero missing links and unchanged
source JSON snapshots. That run validates the analytics implementation commit
`c38e288fea9da1e238f4f80a1e88eb4014b71d4e`.

The first mobile CI stopped before browser execution because Playwright 1.56.1
does not support the runner's Ubuntu 26.04. The existing fix proposed in PR #36
is reused here: pin only this job to `ubuntu-24.04`. The analytics build and
browser checks are now included in that job. Its final rerun is recorded in the
pull request's checks; none of the existing mobile checks are removed.

No test establishes receipt in a live NAVER report. After the owner approves this
candidate and it is deployed, visit the public site, allow analytics and confirm
its ID and pageview in NAVER's real-time report.

## Operation and rollback

Use the repository's existing reviewed-commit deployment procedure. Do not change
the deployment approval inputs or scheduling to publish this candidate.
Reverting this change removes the loader and its two assets from the public build.
Existing local choices can remain inert; no personal records need to be cleared.

## Provider references

- Installation: https://naver.github.io/conversion-tracking/pages/07_naver_analytics_guide/
- Information received: https://help.naver.com/service/9864/contents/15398?osType=PC
- Report retention: https://help.naver.com/service/9864/contents/15397?lang=ko&osType=PC
- Cookie-based visitor measurement: https://help.naver.com/service/9864/contents/17624?lang=ko&osType=PC
