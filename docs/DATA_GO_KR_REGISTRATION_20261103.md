# Public Data Portal recruitment API registration check — 2026-11-03

## Requested service

The user supplied an approved development application for
`재정경제부_공공기관 채용정보 조회서비스`, valid 2026-10-13 through 2028-10-13.
The approval statement is user-provided; actual authentication is recorded separately.

Official service: https://www.data.go.kr/data/15125273/openapi.do
Official metadata: https://www.data.go.kr/catalog/15125273/openapi.json

The service page's inline `swaggerJson` was read directly on 2026-11-03.
It defines `GET https://apis.data.go.kr/1051000/recruitment/list` and
`GET https://apis.data.go.kr/1051000/recruitment/detail`.
Both require the query parameter `serviceKey`; detail also requires integer `sn`.
`resultType=json` selects JSON. List pagination uses `pageNo` and `numOfRows`,
with `ongoingYn=Y` for ongoing notices. Normal codes documented are 0 and 200;
response structure and official notice IDs must also validate.

The list schema explicitly says `files` and `steps` are empty and must be
obtained from the detail operation. A list response alone is not complete
attachment or recruitment-stage verification.

## Separate validation path

`data_go_kr.py` is a dedicated client fixed to the public-data API host.
`scripts/verify_data_go_kr_live.py` reads `DATA_GO_KR_KEY` and creates review
artifacts only. The isolated workflow now maps repository Secret
`DATA_GO_KR_KEY` into that variable. Keep the existing `ALIO_KEY` for the
separate ALIO OpenData path. No credential is copied from one service to the
other automatically. Neither secret is read or changed through repository code.

The existing ALIO OpenData collector/check files are unchanged by this addition.
There is no automatic fallback from one service to the other, and no arbitrary
endpoint override or cross-host redirect with a credential.

## Verification scope and data protection

- Fetch all ongoing list pages, at most 10 pages of 100; reject incomplete,
  duplicate, inconsistent, invalid or oversized pagination results.
- Verify up to three independent detail IDs. Preserve full sample `files` and
  `steps` in `candidate/detail-samples.json`. The report states `sample_only`;
  all remaining notice detail endpoints remain unverified.
- Reuse established display conversion, retain old notices and old detail
  fields, and write merged JSON only beneath the isolated artifact directory.
- Check both repository snapshot hashes before completion. No data commits,
  deletions, publication, main edits, or scheduled collection are performed.
- Report additions, changes, date expiration and absence separately. Absence
  from the ongoing list does not prove official early closure.
- Do not log credentials, request URLs with query strings, raw errors, or
  response bodies. Reject candidate artifacts if a credential form appears.

The workflow runs only for the specified new verification files on the
restoration branch and uses `contents: read`. It has no schedule or deployment
step. Its `report.json` and candidate files are retained as Actions artifacts
for seven days. Production deployment and regular collection remain pending
the user's separate authorization.

## Actual registration result and remaining user input

At 2026-11-03 12:37:58 KST, the initial isolated check using the existing
`ALIO_KEY` made one list request and received HTTP 403. Both 520-record
source snapshot hashes were unchanged. No detail request or candidate was made.

At 2026-11-03 12:40:25 KST, one bounded diagnostic request to the same official
list endpoint confirmed the gateway token `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`,
official error code `30`, with HTTP 403. The response body and key were not logged
or saved. The parallel ALIO work had updated the branch snapshot to 610 notices;
both files were again preserved byte-for-byte. This requested public-data API
check added or changed no notices and made no detail requests.

Evidence:
- Initial run: https://github.com/kllollain-max/careerpick/actions/runs/41573348839
- Diagnostic run: https://github.com/kllollain-max/careerpick/actions/runs/41573580336
- Official error guide: https://www.data.go.kr/tcs/dss/selectErrCodePopupView.do
- Diagnostic source SHA256 for alio.json:
  `becc777857fcb5122a36f134480ee39326b1a8b00e55e18759e980ff54d5f04d`
- Diagnostic source SHA256 for alio-detail.json:
  `f40a642608d34a89239aa1650e85241fe6bf72acde6576ec58e10130850e4185`

The public portal's development application is approved according to the user,
but the tested existing credential is not registered at this gateway. Save the
public-data portal's own service key as repository Secret `DATA_GO_KR_KEY` at
https://github.com/kllollain-max/careerpick/settings/secrets/actions/new.
Use the decoded key when the portal displays both encoded and decoded forms.
Do not overwrite the working `ALIO_KEY`, paste a key into chat, or commit it.
The workflow requires this dedicated secret and never falls back to `ALIO_KEY`.
After entry, rerun the failed job for the dedicated-secret workflow revision;
no main merge, deployment, or schedule is needed to verify registration.

Targeted verification: 11 adapter tests plus 4 isolated-runner tests passed
locally, including safe gateway diagnostics and credential-echo rejection.
Network registration remains pending a successful request with the dedicated
public-data key; no delta counts or full-detail success are claimed.
