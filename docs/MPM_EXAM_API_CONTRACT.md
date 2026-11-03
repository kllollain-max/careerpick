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
- Current row schema contains seven strings: `시험명`, `선발예정인원`,
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
envelopes, inconsistent counts, duplicate rows, or unverified dates. Only safe
error codes and a bounded public summary are returned; raw responses,
credential-bearing URLs, keys and exception messages are not exported. The
module never writes to existing ALIO snapshots or website files.
