# ALIO live connection readiness — 2026-11-03 KST

## Verified scope
Repository: kllollain-max/careerpick. PR #1. Reviewed source HEAD: 7e7cde823aa751548b78407270ef8a3e61f74325.
The 1,219-file tree equality check and successful functional/browser checks are reused without rerunning.

## Credential state (names only)
Authenticated GitHub Settings → Secrets and variables → Actions showed:
- Repository secrets: "This repository has no secrets."
- Environment secrets: "This environment has no secrets."
- ALIO_KEY in this executor: absent.
No secret value was read, copied, displayed, added, changed or requested through chat.
This is a missing-credential finding, not an authentication rejection or API permission result.

## API contract review
alio.py uses https://apis.data.go.kr/1051000/recruitment/list with a decoded serviceKey from ALIO_KEY, resultType=json, pageNo, numOfRows=100 and ongoingYn=Y. It accepts the legacy result/totalCount schema and response.header/body.items.item schema.
convert() validates basic serial/title/end-date and uses a<recrutPblntSn> as the notice ID. detail_of() derives the site's detail JSON from fields in the LIST response. It does NOT issue a separate detail API request.
The newer /v1/recruit/list.do and /v1/recruit/detail.do contract is not implemented or validated. A key for the newer service must not be assumed compatible with this legacy endpoint. Official catalog retrieval did not provide a usable contract in this session.
No authenticated API request, listing response, separate detail response, attachment binary or actual API authorization success was observed.

## Isolated preflight actually executed
Copied alio.py, scripts/collect_alio.py and both snapshot JSON files to a temporary isolated directory, with ALIO_KEY absent.
python3 scripts/collect_alio.py exited 2 and returned:
{"status":"blocked_missing_secret","secret":"ALIO_KEY","changed":false}
Source and temporary-copy SHA256 values remained unchanged.
Actual API requests: 0.
This is a missing-key guard check, not a live collection or simulated authentication success.

## Dataset
Before: 520 unique ALIO notices; updated=2026-10-30T23:43:53+09:00.
After: 520 unchanged archived notices; same updated timestamp.
New collection timestamp: none.
Additional/modified/newly closed notices: not computable without a live response; NOT reported as zero.
alio.json SHA256: 8aa63adf95f679d3fba235fe572c40bed8794f6dc435bb55a16fbaf8df1b3e79.
The page's clock-based deadline calculation is not proof of current official reception status.

## Data and publishing review
scripts/collect_alio.py stages both snapshots, validates IDs/detail identity, merges by ID while retaining archived rows, and rolls back the JSON pair after ordinary write exceptions. Empty/incomplete/failed API collection does not replace the source.
The preserved collector emits no separate detail API request. Full live contract verification remains a blocker.
No data changed, so no changed-notice rendering/search/storage compatibility tests were necessary.
Existing dist/: 1,198 files; forbidden internal/backups/executable paths=0. Private-key/GitHub-token signature matches=0. Signature checks are not an exhaustive guarantee of absence of every possible secret.
Reused build validation already verifies the allowlisted static output. Only dist/ is a Pages artifact.
review-workflows/deploy-pages.yml.disabled and collect-alio.yml.disabled remain inert. Active verification workflow is workflow_dispatch only. main has no workflow files; branch-only workflow_dispatch does not currently supply a proven premerge run route. Do not merge merely to access a secret.
No scheduler, public visibility change, Pages configuration, deployment, main merge, other repository or blog schedule was changed.

## Minimal user action and resumption
1. In https://github.com/kllollain-max/careerpick/settings/secrets/actions select New repository secret.
2. Name it ALIO_KEY; enter the decoded key for the LEGACY data.go.kr service used above. Do not send the key to chat.
3. If the available key is for the newer /v1 service, provide the official non-secret API documentation/service URL instead; keep it distinct from the legacy key.
4. After key registration and contract identification, prepare a reviewed one-time branch-scoped candidate execution route that can access repository secrets without a main merge. Run in isolation, emit only a validated candidate pair and sanitized status/counts, and do not commit automatically.
5. Verify list/detail response structure and official links; compute new/changed/closed counts, preserve the old timestamp separately, and commit only validated candidate data to the recovery branch.
6. Test only changed notices and compatibility. Any new response/contract failure leaves the archived 520 rows untouched.

## Deployment approval (not requested before live verification)
Only after the above blocker clears: approve the exact final PR HEAD for main merge, visibility change only if Pages hosting requires it, Pages activation and one manual deployment. Scheduled collection requires its own approval and is excluded.
Target: https://kllollain-max.github.io/careerpick/.
Rollback: retain the verified static artifact and snapshot pair; redeploy the last approved artifact/commit through the manual Pages path. Do not overwrite historical snapshots or delete users' browser storage.
