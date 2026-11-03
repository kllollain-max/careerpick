# ALIO new contract verified in signed-in official UI — 2026-11-03
Source: https://opendata.alio.go.kr/new/odaApiUserInqDataMng/openApiRecrutDetail.do
Official title: 재정경제부_공공기관 채용정보 조회서비스 1.0.0.
POST https://opendata.alio.go.kr/new/v1/recruit/list.do
POST https://opendata.alio.go.kr/new/v1/recruit/detail.do
Parameters are in query (not JSON body). serviceKey required in both; sn required for detail.
List pageNo default 1, numOfRows default 10, ongoingYn Y/N, resultType json.
Envelope: resultCode=0 success, resultMsg; list result array + totalCount; detail result object.
Detail includes files[] metadata and steps[]. Existing UI flattening is preserved; the new live check verifies one independent detail identity.
Code 7 authentication error; 8 application approval failure; 3 no data; 10 invalid parameter; 11 missing required parameter.
No interchange with the legacy data.go.kr key. No credentials copied from browser.
Local validation: 3 contract test methods passed (POST/query encoding, list envelope/identity rejection, safe errors); original partial-fetch guard passed. Missing-key live runner preserves source bytes. These are not authenticated success.
The ALIO live check workflow runs only on push to the existing restoration branch for the four named paths. No schedule, deployment, write permissions, data commits or main changes. Candidate pair and sanitized report are uploaded as a private Actions artifact. GitHub key presence and approval are determined by this run, not assumed.
Date-expired counts are not official early-closure verification. Candidate remains review-only.

Live server observation: resultCode 200 (run 41572665238) differs from Swagger example 0. Accept 0/200 only alongside strict list envelope/count and detail ID validation. Key presence confirmed by Actions, value never logged.
