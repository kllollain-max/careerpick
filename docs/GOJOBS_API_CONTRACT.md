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
- Optional source links are evaluated separately: only valid absolute HTTP(S) references are returned; absent/unusable references are reported with fixed status tokens. Their raw unusable values are omitted. Neither source pages nor attachments are downloaded or source URLs synthesized.
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

A follow-up failure now exposes only `last_response_diagnostic.observed_filters`: the requested public enum codes and the two observed enum codes (or `unknown`). Arbitrary response values, raw payloads and credentials are excluded. Validation remains strict on code meaning and the requested filters.

### Observed field reversal confirmed

Read-only diagnostic run [41580523270](https://github.com/kllollain-max/careerpick/actions/runs/41580523270), code HEAD `f7592fc`, observed `type01=e01`, `type02=g02` when requesting `Pblanc_ty=e01` and `Instt_se=g02`. This establishes that the actual list swaps the response field meanings compared with the documentation; the query parameter names themselves match the official specification.

The adapter now recognizes exactly two unambiguous layouts: `type01` in the documented `g` namespace with `type02` in the documented `e` namespace, or the observed opposite. Both are normalized to institution/recruitment meanings before checking the exact requested `g02` and `e01`/`e02` values. Two `g` codes, two `e` codes, or unknown codes are rejected. Details are normalized independently and must still match list ID, title and normalized categories. `observed_field_layouts` records fixed tokens for the actually observed list and detail layouts. This correction does not assume that detail or the remaining fields have already passed live validation.

### Optional source links kept separate from essential detail validation

Run [41580701424](https://github.com/kllollain-max/careerpick/actions/runs/41580701424), code `4268ca508a6e6bf7f13ac43057a2e159a1538cf4`, verified both list queries and reached the first detail, but the old adapter failed `invalid_source_link` for an optional `link01`/`link02`/`link03` value. That error alone does not establish the original value's format; raw link content was not logged.

The specification describes those link fields as strings/URLs and gives no relative-URL base. Therefore the adapter does not guess, resolve, or follow unusable references. It now retains only structurally valid absolute HTTP(S) links and reports fixed per-field statuses (`not_provided`, `relative_reference`, `schemeless_reference`, `unsupported_scheme`, `credential_component_rejected`, `invalid_url`, `validated_http_url`). The report separately counts validated, absent and unverified link slots. API/detail success never means every source link or linked page was verified. ID, title, normalized categories, list/detail identity and content-presence checks remain in place, as does credential-echo rejection before optional fields are processed.

## Partial-verification progress retained

Follow-up run [41584479030](https://github.com/kllollain-max/careerpick/actions/runs/41584479030), code `e55c1a185e1abcbf1ee6ccd9162ac05c385b1467`, records successful authentication independently of final sample integrity. The client exposes `verification_progress` with validated list rows, details cross-checked against those rows, link counters, and the public ID plus expected categories of a rejected detail. The runner emits only bounded, credential-checked context. Strict validation and the nonzero overall exit are unchanged.

The observed first page contained five historical `e01` records with deadlines in 2008–2009. The `e02` query returned zero rows. IDs `4` and `7` passed detail checks; both were `e01`. ID `20` (임실치즈과학연구소 선임연구원 채용공고) failed because detail classifications did not form an accepted pair (`type01=g01`, `type02=unknown`). This is not evidence of current active recruitment or a verified `e02` detail. Sort direction remains unverified; no sorting parameter or acceptance rule was changed to make this check pass.

See [the current result](ADDITIONAL_API_CONNECTION_CHECK_20261103.md) and [sanitized follow-up evidence](evidence/gojobs-followup-20261103.json). The 23 adapter tests include partial-progress preservation, rejected-detail exclusion, failed-ID safety, and reset between verification attempts.
