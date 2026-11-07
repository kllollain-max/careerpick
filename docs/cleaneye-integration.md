# Cleaneye recruitment integration

## Current state — 2026-11-07 KST

PR #28 was merged and the Cleaneye source is now enabled in production. The employment service and the separate province-code service are approved development accounts for 2026-11-07 through 2028-11-07. The province-code approval blocker has been resolved using the existing protected public-data credential.

The first complete protected collection, captured at **2026-11-07 12:57:55 KST**, obtained the official 2026 codes for all **17 regions** and **351 unique recruitment notices**. It made one province-code request and 17 employment requests, with all 18 requests successfully interpreted. Region `007005` had no matching records. The run produced an isolated candidate and preserved the existing source snapshots; it did not publish a feed.

Inspection of that real response identified optional fields containing the literal string `null`, employment labels not yet recognized by the filters, and three unusually distant source deadlines. The candidate now handles those values explicitly while retaining notice identities, official links, and meaningful source fields. The final protected collection and browser verification below confirmed those changes.

### Pre-release candidate evidence

**Verification status: Passed: complete protected collection and actual-data browser checks.**

| Check | Final result |
| --- | --- |
| Candidate commit | `bed712cbbb74b7a208d93b7b696f6362cbe305da` |
| Workflow | [Final candidate run](https://github.com/kllollain-max/careerpick/actions/runs/42337471525) |
| Collection timestamp | `2026-11-07 13:13:31 KST` |
| Collector state | `changed` |
| Region coverage | `17` official regions; all declared counts checked |
| Received / stored notices | `351` / `351` |
| Open / upcoming / verification pending | `265` / `81` / `5` |
| Far-future source deadlines requiring review | `3` |
| Source preservation | `true; original snapshots unchanged` |
| Local / workflow regression checks | `67 Cleaneye Python tests; 10 existing GOJOBS/operation Python tests; 74 Cleaneye/homepage/storage/navigation Node tests; all passed` |
| Build and link checks | `1,447 output files; 35,053 HTML links checked; zero missing local links; source JSON unchanged` |
| Actual-data browser checks at 320 / 390 / 1440 px | `All three widths passed: source labels, exact official link, search, saved notices, detail reload, application persistence, prior saved/application preservation; zero overflow and page errors` |

The final collection report confirms **265 open, 81 upcoming, and 5 requiring verification** from 351 notices. The five are two date-only notices closing on the collection date and three far-future source dates. `received` counts all retrieved notices; it must not be described as the number accepting applications.

The pre-release candidate SHA-256 is `6df47aa587edf0a8a12b5713ff43695c241226e491804a68cfcbefe043a7b229`. The downloaded artifact and the candidate were independently checked against their recorded hashes; the 320 px list and detail screenshots were visually reviewed.

### Verified production release

The owner authorized release on 2026-11-07. [PR #28](https://github.com/kllollain-max/careerpick/pull/28) was merged as `56c9085a504ed0a1719c31fab559ef987dd6ba9f`. [Operation run 42338197158, attempt 2](https://github.com/kllollain-max/careerpick/actions/runs/42338197158/attempts/2) completed with `overall=success`, `storage=success`, `deployment=success` and `public_check=success`.

The production collection timestamp is **2026-11-07 13:27:15 KST**. All 17 regions were checked: **351 notices, 265 open, 81 upcoming and 5 requiring verification**. The committed data revision is `b844bd9485fa32b7cc878bd73947e5951856d122`; the Cleaneye snapshot SHA-256 is `c3b4695baaae4bd12f179971148bcf64d09e77f38e38d78de25eff7c6908ab46`. The published snapshot matched the committed data in the public hash check, which passed at 13:30 KST.

A browser check on the public site found the newly collected Wonju Facilities Management Corporation notice and opened its details with the correct original link: [published notice 80661](https://kllollain-max.github.io/careerpick/#job=cleaneye-80661). Notice IDs, original dates, source URLs and source employment labels passed independent checks on all 351 committed records.

Attempt 1 stopped on `transport_failed` after five successful regional employment responses. It preserved all baseline files and did not deploy. Attempt 2 completed the entire collection. The earlier diagnostic does not identify the underlying transport exception type.

## Official API contracts

| Service | Official specification | GET endpoint | Parameters |
| --- | --- | --- | --- |
| Recruitment | [15159757](https://www.data.go.kr/data/15159757/openapi.do) | `https://apis.data.go.kr/B551982/openApiEmployInfo/openXmlEmployInfo` | `serviceKey`, `sidoCd`, `type=xml` |
| Province codes | [15061217](https://www.data.go.kr/data/15061217/openapi.do) | `https://apis.data.go.kr/B551982/openApiSidoCd3/openXmlSidoCd2` | `serviceKey`, `pageNo`, `numOfRows`, `type=xml`, `ac_year` |

The employment specification has no page-number or date filter. For a normal successful response, each region must return exactly its declared `totalCount`; incomplete responses are rejected. Province codes are paginated and independently checked for completeness. Employment requests use the returned official codes unchanged, rather than assuming codes from another administrative system.

The official employment Swagger describes XML root `response`, a header containing `resultCode` and `resultMsg`, and a body containing `items` and `totalCount`. Its documented element names are `openXmlEmployInfo-header` and `openXmlEmployInfo-body`. The current Swagger does not enumerate provider result-code meanings or show the no-data variant.

### Region with no matching employment records

[Bounded diagnostic run 42336052565](https://github.com/kllollain-max/careerpick/actions/runs/42336052565) observed the exact provider pair `resultCode=3` and `resultMsg=NONOTEXISTDATA_ERROR`, without a body, for officially verified region `007005`. The collector accepts this exact pair only for an employment-list response and only when its optional body is unambiguously empty. If present, `totalCount` must be zero and `items` must contain no records or unexplained text. Contradictory fields, duplicate fields, unexpected messages, nonzero counts and malformed XML remain errors.

This exception does not apply to province-code lookup, HTTP errors, authentication failures, or arbitrary code-3 responses. A valid empty region no longer aborts the other regions. An entirely empty new feed still cannot replace the baseline or be published as a successful initial collection.

Credentials come from `CLEANEYE_KEY`, falling back to the existing GitHub secret `DATA_GO_KR_KEY` in the workflow. `ALIO_KEY` is not used. Requests remain on the fixed HTTPS API host and do not follow redirects. Typed timeouts, connection errors and temporary DNS failures (EAI_AGAIN) are retried for the same idempotent GET up to three total attempts, waiting 1 and 2 seconds. HTTP, SSL, API and payload-validation failures are not retried. Actual attempts are counted separately from successfully validated responses, and exhausted retries still reject incomplete collections. Unknown error strings are not interpreted as temporary failures. Logs contain bounded diagnostic codes and counts, never credential-bearing request URLs or raw exception strings.

## Data mapping and preservation

- The public identity is `cleaneye-` plus the unchanged official `NO`. Similar titles from other sources do not prove a duplicate. IDs remain within the existing saved-record format's 128-character limit.
- `ENT_TITLE` and `ENT_NAME` supply the title and institution. `WORK_PLACE` supplies the workplace; the institution's `SIDO_CD` remains separate as `sourceRegion` and is never substituted for a missing workplace.
- The exact string `null` observed in optional source fields is treated as a missing value. It is omitted from detail/search text; missing headcount is `null`, not zero. Required identifiers, title/institution fields, and date validation are not silently relaxed.
- `PUB_DATE` is the application start and `PUB_END_DATE` is the application end. Neither `PUB_DATE` nor `UPD_DATE` is invented as a publication date; `pub` remains `null`.
- A source date without a time keeps `dueHasTime=false`. The internal end-of-day value is a sorting surrogate, not a source-supplied closing time. A date-only notice closing today requires verification rather than being declared open for the whole day.
- A deadline whose year is at least 10 calendar years beyond the collection year receives `deadlineReviewReason=far_future_source_date`. An otherwise open/upcoming notice is marked `verification_pending`. The threshold requests source review; it does not prove an upstream error or closure. Original dates, source status and source links remain intact.
- Notices with that date-review flag show the full source year and `원문 마감일 확인 필요` / `일정 확인` instead of a large D-day countdown. Existing closed/cancelled states retain their meaning.
- Observed employment labels, including `일반정규직`, `일반계약직`, `전문계약직` and `비상임`, remain visible as source values. Filter aliases map the first three to their appropriate regular/contract groups; `비상임` is not guessed to be regular or contract. Unknown coded values are not inferred from titles, and nonregular employment does not match regular employment by substring.
- Source-provided individual URLs are validated against the official HTTPS Cleaneye job hosts. Missing or unexpected forms block the candidate. Filenames are not converted into invented download links.
- Meaningful source fields remain available under Korean detail labels. HTML is displayed as inert text; new institutions do not receive links to nonexistent local history pages.
- Collection writes only `cleaneye-operation-output/`. Existing root/data JSON snapshots must remain byte-identical during candidate collection.
- Failed authentication, incomplete regions, duplicate IDs, an unexpectedly large decline, an unusable initial candidate or an invalid link never replaces the previous feed. Previously stored records are retained rather than deleted. A missing future notice becomes status-uncertain.
- Repeating a semantically unchanged collection retains its update timestamp. A complete response may update a known notice to expired or cancelled without deleting it.

### Source values identified during review

The initial real response used the literal string `null` for all 351 workplaces and working-hour fields, 189 preference fields, five headcounts and one institution address. Required notice IDs, titles, institution names and application dates were present. The missing workplace information must not be reconstructed from institution location.

Three source records contained far-future deadlines: `14377` → `2054-07-10`, `49038` → `2400-03-19`, and `67557` → `2050-09-26`. Those dates already appeared in the API source fields. They are preserved and flagged for review, rather than silently changed or counted as confirmed open notices.

The two date-only notices closing on 2026-11-07 were `80648` and `80752`. Their exact closing times were not supplied. These observations describe the reviewed snapshot, not a promise that future source values or counts will remain the same.

## Verification and operation

The candidate workflow has read-only repository permission and two independent checks:

1. Unit/regression checks, a public build, and 320/390/1440 px browser checks with synthetic in-memory responses.
2. Client/preservation checks followed by protected API collection, an isolated build from the verified candidate, and browser checks with the actual collected notices.

Passing the first check is not evidence that the second passed. Acceptance requires a final collector state of `changed` or `unchanged`, verified official region lookup, complete collection, preserved original snapshots, a candidate file with its recorded hash, and successful subsequent build/browser steps. Authentication and collection-completeness flags alone are insufficient if later normalization or validation fails.

The initial tracked baseline used `collectionStatus=not_collected` and an empty list; the production operation has now replaced it with the verified 351-notice snapshot. A not-collected baseline is not a successful zero-job feed. Synthetic records stay confined to tests or disposable browser contexts and are never written to public job data. The actual source candidate is selected only after the complete validation path succeeds.

The operation change adds Cleaneye independently to the existing three-hour schedule. Other sources continue if Cleaneye fails, and the combined report records partial failure explicitly. Public snapshot verification includes `cleaneye.json` after release. The schedule expression, personal-storage keys, push settings and social publication workflows are unchanged.

Merging the PR does not itself trigger the operation. Once production release is authorized, merge the PR and run `CareerPick scheduled operation` (`operations.yml`) on `main`, or allow its next three-hour scheduled run. That operation selects the validated candidate, commits the data, deploys Pages, and verifies public file hashes. A standalone `Deploy approved CareerPick` run does not collect API data.

After production release, verify the deployed revision, `cleaneye_source` result, and public Cleaneye snapshot separately; the overall job result or candidate success alone does not prove that the public site has updated. Rollback can restore the prior frontend/collector while preserving the new source snapshot and users' stored IDs. No migration deletes personal records.

## Earlier diagnostic history

Before province-code approval, the region service returned HTTP 403 / gateway code 30; limited employment probes returned provider code 3 without proving nationwide coverage. Those historical results must not be described as the current access state.

- [First official code lookup and empty-region employment probe](https://github.com/kllollain-max/careerpick/actions/runs/42311038349)
- [Public form and one-region diagnostic](https://github.com/kllollain-max/careerpick/actions/runs/42311226786)
- [Bounded region-format diagnostics](https://github.com/kllollain-max/careerpick/actions/runs/42311515236)
- [Approval recheck, attempt 2](https://github.com/kllollain-max/careerpick/actions/runs/42314290100/attempts/2): province-code lookup succeeded; the old parser then stopped at the valid empty-region response.

Temporary diagnostic workflows are not part of the recurring production collection. Their run history remains available as evidence of the resolved access and parser issues.
