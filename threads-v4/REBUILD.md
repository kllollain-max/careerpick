# CareerPick Threads v4 — isolated rebuild

This branch is an isolated replacement candidate. It does not publish and does not change the existing production schedule.

## Invariants
- Account: @hid_119; publisher user ID must be independently verified before cutover.
- Keep existing CareerPick feeds, homepage, web push, other projects and publication ledger intact.
- Four KST slots: 08:00, 12:00, 16:00, 20:00. Preflight 15 minutes earlier.
- Never turn an unverified notice into an approved draft.
- One main post, zero automatic replies; no URL/hashtags in body; final CTA exactly: 자세한 사항은 프로필링크 확인.
- Alternate IMAGE and TEXT based on independently confirmed published receipts.
- Never retry an ambiguous Meta POST without remote reconciliation.
- Source/official verification, expiry, duplicate and image review are mandatory gates.

## New architecture
1. Source reader: saved ALIO and other approved feeds; rank open permanent posts, exact unit counts, sectors.
2. Official verification: retrieve official source, application window, restrictions, correction/cancellation status and destination page. Fail closed if inaccessible.
3. Writer: deterministic structured manuscript with source refs, checked-at timestamps, SHA-256, reviewed facts and final public copy.
4. Media: generate and visually review card for IMAGE slots, record asset hashes and public reachability; image failure holds IMAGE only.
5. Queue: immutable notice ID + slot claims, optimistic concurrency and readback; target 8 upcoming verified entries, never fabricate readiness.
6. Publisher: single worker, exact account check, receipt reconciliation, publish-once, Meta ID and permalink GET verification, durable ledger.
7. Recovery: classify missing supply, expired source, image, auth, transient API, ambiguous send, persistence; alert on unresolved blockers.

## Cutover acceptance gates
- Existing ledger backup SHA and readback
- Source review with current official evidence
- Full queue validator passes and 1 reviewed manuscript is present
- Duplicate, expired, no-source, image failure, concurrency, token expiry, API timeout, ambiguous POST and ledger-write-failure tests pass
- One controlled real publish yields confirmed Threads ID, permalink, account and ledger receipt
- Only then enable v4 schedules and disable old publisher, avoiding concurrent workers

## Current status
Branch created for rebuilding. Not approved for production cutover; no post claimed.
