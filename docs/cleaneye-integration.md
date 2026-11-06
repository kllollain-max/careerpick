# Cleaneye recruitment integration

## Current state — 2026-11-07 KST

This is a review candidate. The owner approved the employment service development account for 2026-11-07 through 2028-11-07 and requested the integration. The code, UI and scheduled-operation changes are prepared on `codex/cleaneye-api-20261107`; no production merge or deployment is part of the verification workflow.

The employment service responded through the existing protected `DATA_GO_KR_KEY`. Eight bounded employment probes returned HTTP 200 with provider `resultCode=3` and no records. This proves a provider response was obtained, but does **not** prove a complete successful collection or nationwide coverage. The official service documents describe code 3 as no matching data. Do not interpret it as an invalid key, a proven empty nationwide feed, or successful collection.

The required region-code service returned HTTP 403 and gateway `returnReasonCode=30`. Its separate utilization approval has not been demonstrated. Public recruitment/institution pages could not be read because their requests timed out or returned 503. No nationwide code list was inferred from other administrative code systems.

The next prerequisite is approval of the [official province-code service, dataset 15061217](https://www.data.go.kr/data/15061217/openapi.do) on the same public-data account. After that, the collector resolves the source's own current-year codes before requesting employment records. It reuses the existing credential; the user does not need to paste a key into chat.

Read-only probe evidence:

- [First official code lookup and empty-region employment probe](https://github.com/kllollain-max/careerpick/actions/runs/42311038349)
- [Public form and one-region diagnostic](https://github.com/kllollain-max/careerpick/actions/runs/42311226786)
- [Bounded region-format diagnostics](https://github.com/kllollain-max/careerpick/actions/runs/42311515236)

These diagnostic workflows are removed from the final candidate. No guessed region codes are used by the collector. Their history remains available as evidence of the observed blocker.

## Official API contracts

| Service | Official specification | GET endpoint | Parameters |
| --- | --- | --- | --- |
| Recruitment | [15159757](https://www.data.go.kr/data/15159757/openapi.do) | `https://apis.data.go.kr/B551982/openApiEmployInfo/openXmlEmployInfo` | `serviceKey`, `sidoCd`, `type=xml` |
| Province codes | [15061217](https://www.data.go.kr/data/15061217/openapi.do) | `https://apis.data.go.kr/B551982/openApiSidoCd3/openXmlSidoCd2` | `serviceKey`, `pageNo`, `numOfRows`, `type=xml`, `ac_year` |

The employment specification has no page-number or date filter. Each region must return exactly its declared `totalCount`; incomplete responses are rejected. The province-code response does have pagination and is independently checked for completeness.

Credentials come from `CLEANEYE_KEY`, falling back to the existing GitHub secret `DATA_GO_KR_KEY` in the workflow. The unrelated `ALIO_KEY` is never used. Requests stay on the fixed HTTPS API host and do not follow redirects. Logs contain bounded diagnostic codes and counts, never credential-bearing request URLs or exception strings.

## Data mapping and preservation

- The public identity is `cleaneye-` plus the unchanged official `NO`. Similar titles from other sources do not prove a duplicate. The identity stays within the existing saved-record format's 128-character limit.
- `ENT_TITLE` and `ENT_NAME` supply the title and institution. `WORK_PLACE` supplies the workplace; the institution's `SIDO_CD` does not substitute for it.
- `PUB_DATE` means application start. `PUB_END_DATE` means application end. Neither `PUB_DATE` nor `UPD_DATE` is invented as a publication date; `pub` remains `null`.
- A source date without a time remains `dueHasTime=false`, including on its closing day. Unknown or contradictory dates do not establish open reception.
- Employment and status fields retain the source values. Unknown coded values are not guessed from a title. A nonregular position does not match regular employment by substring.
- The source-provided individual URL is validated against the official HTTPS Cleaneye job hosts. Missing or unexpected link forms block the candidate until supported by real response evidence. Filenames do not become invented download links.
- All source fields remain available under Korean detail labels; HTML is displayed as inert text. New institutions do not receive links to nonexistent local history pages.
- Collection writes only `cleaneye-operation-output/`. Existing root/data JSON snapshots must remain byte-identical during collection.
- Failed authentication, incomplete regions, duplicate IDs, an unexpectedly large decline, no usable initial candidate or an invalid link never replaces the previous feed. Previously stored records are retained rather than deleted. A missing future notice becomes status-uncertain.
- Repeating a semantically unchanged collection retains its update timestamp. A complete response may update a known notice to expired or cancelled without deleting it.

## Verification and operation

Local verification passed 54 Cleaneye Python tests, 68 frontend/storage/navigation Node tests and 10 existing GOJOBS/operation Python tests. The public build produced 1,447 files, checked 35,053 HTML links with zero missing local links, and preserved the original source JSON hashes. Browser results are recorded separately by the candidate workflow; these unit/build results are not live API success.

`cleaneye.json` begins with `collectionStatus=not_collected` and an empty list. It is not presented as a successful zero-job collection. All synthetic test records are confined to tests or fulfilled in memory inside a disposable browser context. They are never written to the public feed.

The candidate workflow has read-only repository permission and two independent checks:

1. Unit/regression checks, a public build, and 320/390/1440px browser checks using synthetic in-memory responses.
2. Client/preservation tests followed by an actual protected API collection; only a verified live candidate proceeds to a separate build and browser check. This job runs independently so a browser-installation delay does not hide an API-approval error.

Passing the first check must not be reported as passing the second. The live check is expected to remain blocked until the region-code service is approved and its real response is validated.

The operation change adds Cleaneye independently to the existing three-hour schedule. Only a successful, complete, source-preserving candidate is selected. Other sources continue if Cleaneye fails, and the combined report records partial failure explicitly. Public snapshot verification includes `cleaneye.json` after release. The schedule expression, personal-storage keys, push settings and social publication workflows are unchanged.

Production merge and deployment remain subject to the owner's existing separate approval requirement, after live collection is reviewable. Rollback can restore the prior frontend/collector while preserving the newly stored source snapshot and users' saved IDs; no migration deletes personal records.
