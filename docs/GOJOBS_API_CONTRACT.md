# GOJOBS public recruitment API: isolated verification

## Official contract checked 2026-11-03

Service: **인사혁신처_공공취업정보 조회 서비스** (data.go.kr dataset `15156780`).

Primary sources:
- https://www.data.go.kr/data/15156780/openapi.do — inline `swaggerJson` read from the original page HTML.
- https://www.data.go.kr/catalog/15156780/openapi.json — official distribution metadata.

Both sources identify HTTPS gateway base `https://apis.data.go.kr/1760000/PblJobService`.
The inline specification also contains an older HTTP upstream URL; the adapter uses only the HTTPS gateway and blocks redirects.

| Operation | Method/path | Parameters used in this check |
|---|---|---|
| Recruitment list | `GET /getList` | `serviceKey`, `Pblanc_ty`, `Instt_se`, `Sort_order`, `pageNo`, `numOfRows` |
| Independent detail | `GET /getItem` | `serviceKey`, `idx` |

The repository secret **GOJOBS_KEY** is the intended runtime credential. It must be supplied by the isolated workflow, not committed, printed, or copied from other service secrets.

`Pblanc_ty=e01` is public competitive recruitment and `e02` is career competitive recruitment. `Instt_se=g02` selects local-government civil-servant recruitment. `Sort_order=1` is the official example value; this implementation does not infer or claim its sort direction.

The list returns XML `response/header` containing `resultCode`/`resultMsg`, and `response/body` containing `totalCount`, `numOfRows`, `pageNo`, and `items/item`. The list items contain `idx`, `title`, `insttname`, `type01`, `type02`, `enddate`, `regdate`, `moddate`, `areacode`, and `readnum` in the documented schema.

The detail schema returns `response/body/item` with `idx`, `title`, `type01`, `type02`, `contents`, and `link01`/`link02`/`link03`. File metadata and positions have separate documented endpoints (`getItemFile` and `getItemPosition`), which this bounded registration check does not call.

## Deliberately bounded scope

- Two list calls: page 1, at most five rows each, for local-government public/career recruitment.
- At most three independent details, selecting at least one record from each nonempty recruitment type before filling the remaining slot.
- Maximum five API requests in one successful verification; no full collection or production snapshot update.
- Report totals per filter, returned sample count, IDs, titles, organizations, parsed dates, supplied source links, and verification counters.
- No claim that list totals are active opportunities, no inferred official closure, and no claim that this API covers every local exam schedule.
- Source links are validated for ordinary HTTP(S) structure and reported as provided; neither their pages nor attachments are downloaded.
- An authentic but empty list is explicitly reported with `empty_list=true`, `detail_verified=false`, and `detail_status=unverified_empty_list`. It is not an independent-detail success.

## Credential and failure handling

The client uses a fixed allowlisted gateway and operations, percent-decodes an encoded input key once before URL encoding, and rejects redirects. It has a 25-second request timeout and a 2 MB response cap. DTD/entity declarations are rejected before XML parsing. The adapter refuses response content echoing the credential in raw, URL-encoded, decoded, or XML-entity form.

HTTP success is insufficient: an accepted application result code and expected XML structure must validate. IDs, page totals, unique records, category filters, date formats, and detail/list identity are checked. Exception messages expose safe codes only; request URLs with queries, raw API payloads, and credential values are never logged or returned by this module.

No live result is claimed by this contract document. Actual authentication and response compatibility are established by the separately recorded GitHub Actions run with the registered secret.

## Offline tests

`python -m unittest discover -s tests -p test_gojobs.py`

The focused tests cover valid list/detail contracts, distribution across both recruitment types, three-detail bounds, empty results, application authentication errors, safe HTTP gateway diagnostics, raw/encoded/XML-entity credential echoes, encoded-key normalization, redirect rejection, identity mismatch, duplicates/filter/page/date failures, oversized/XML-DTD responses, and safe transport errors.

## Response classification diagnostics

The official specification names `type01` as the institution code (`g01`–`g04`) and `type02` as recruitment type (`e01` etc.). The first live check reached valid XML but failed `filter_mismatch`. That alone does not distinguish a parameter issue from a reversed-field response.

A follow-up failure now exposes only `last_response_diagnostic.observed_filters`: the requested public enum codes and the two observed enum codes (or `unknown`). Arbitrary response values, raw payloads and credentials are excluded. Validation remains unchanged until the observed codes establish the exact discrepancy.
