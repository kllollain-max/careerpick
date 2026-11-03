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
artifacts only. The isolated workflow explicitly maps the user's previously
registered repository Secret `ALIO_KEY` into that variable for this requested
service check. It does not read or change the stored secret value and does not
claim that the key is valid until a real response succeeds.

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
