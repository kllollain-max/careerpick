# MPM national civil-service examination calendar contract

Checked on 2026-11-03 against the official sources below. This is an isolated
API connection check, not website publication or recurring collection.

- Data listing: https://www.data.go.kr/data/3033611/fileData.do
- Authoritative Swagger: https://infuser.odcloud.kr/oas/docs?namespace=3033611/v1
- Current dataset title: `인사혁신처_국가공무원 시험일정_20260216`.
- Fixed endpoint: `GET https://api.odcloud.kr/api/3033611/v1/uddi:99fb67de-ddf5-4a3e-8cfb-d3193c7156c5`.
- Authentication: the Swagger permits `serviceKey` query authentication or an
  `Authorization` API-key header. This adapter uses `serviceKey` and receives its
  credential from the runner's dedicated `MPM_EXAM_KEY`, never from another API.
- Query parameters: `page`, `perPage`, `returnType`; JSON is requested explicitly.
- Successful response: HTTP 200 with integer `page`, `perPage`, `totalCount`,
  `currentCount`, `matchCount` and array `data`. HTTP 401 and HTTP 500 are listed
  as authentication/server errors. There is no ALIO-style `resultCode` envelope.
- The published row schema describes seven strings: `시험명`, `선발예정인원`,
  `원서접수기간`, `시험단계구분`, `시험장소공고일`, `시험일`, `합격자발표일`.

The listing describes an annual file-derived API and reports 28 rows. The
adapter does not assume that row count: it verifies the actual complete
response, up to two pages of 50 rows. A stage row is not a separate hiring
notice, and selection counts repeated across stages are not summed.

The 2026 endpoint is pinned rather than silently selecting another year. Date
fields are checked for calendar validity, order, and year. Blank or explicitly
unscheduled cells stay unresolved; the official listing specifically allows
blank place-announcement dates for some document-screening stages. Month/day
dates use the official dataset's 2026 year and this inference is counted in the
report. Verification does not establish that official amendment notices have
all been reflected, and does not claim any 2027 calendar coverage.

All requests use fixed HTTPS endpoints, reject redirects, have a 20-second
timeout and a 1 MiB response bound, and fail on credential echoes, malformed
envelopes, inconsistent counts, duplicate rows, or unverified dates. The existing verify() interface returns a bounded public summary; collect()
additionally returns all validated records within the same 100-row limit. Raw
HTTP responses, credential-bearing URLs, keys and exception messages are not
exported. The
module never writes to existing ALIO snapshots or website files.

For a live response that passes the envelope/count checks but differs from the
documented row types, `last_response_diagnostic.field_types` exposes only the
seven fixed schema names and the observed JSON type names. It never includes
cell values or unexpected source keys. The documented string contract remains
enforced until an actual differing type has been confirmed; a schema error does
not silently become a successful connection check.

## Observed nullable place-announcement field

The diagnostic run
https://github.com/kllollain-max/careerpick/actions/runs/41580523270
at code revision `f7592fc` confirmed strings in all fields except
`시험장소공고일`, which contained both `str` and `NoneType`. This agrees with the
official listing's explicit blank-field note for document-screening place
announcements. The adapter therefore converts JSON null to an empty string in
**that field alone**, counts it as `null_place_announcement_cells`, and skips
date parsing for that empty cell. It does not infer a place-announcement date.
All other fields retain their documented string requirement, including
`선발예정인원`; integer selection counts were not observed or newly allowed.

## Complete candidate records and offline validation

`Client.collect()` returns `records` and `verification` after one complete bounded
pagination pass. `verify()` delegates to it and returns the unchanged summary
contract. Call collect directly when records are needed; do not verify then fetch
again. Partial, duplicate, invalid or credential-containing responses return no
candidate.

`validate_records(records, expected_count=...)` validates saved data without a
key, network, filesystem or timestamp. It returns independent normalized rows
and aggregate metadata, preserving original date text. Saved row content alone
does not establish source completeness, retrieval time or freshness.

The candidate builder converts validated source dates to the existing calendar
page format, preserves pre-display values separately, and refuses ambiguous
multiple-date lists. Its default mode uses the preserved October snapshot and
does not refresh its retrieval timestamp. The manual live mode is separate from
production publication and scheduled collection. See
[the candidate verification report](ADDITIONAL_API_CANDIDATE_20261103.md).
