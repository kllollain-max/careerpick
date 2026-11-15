# CareerPick Threads reviewed-queue bridge v2

This supplies reviewed manuscripts to the publisher queue, but never approves unverified hiring claims.

## Inputs
* Main: current ALIO source, detail, operations, published ledger, writer policy and validators
* State branch: threads/reviewed-staging.json (version 1, entries list) and threads/writer-queue.json
* The writer automation must place complete source-reviewed entries into staging using exactly the publisher queue schema. A draft memo is not a ready entry.

## Fifteen-minute preflight
The existing Threads workflow checks staged drafts at 07:45 / 11:45 / 15:45 / 19:45 KST. The dedicated job:
1. Checks current source identities and policy hashes.
2. Reads latest staging and queue through GitHub Contents API.
3. Rejects published, pending, used, duplicate or expired entries.
4. Runs the actual publisher review, public copy, and image/card checks.
5. Uses a SHA-constrained CAS write and exact readback to append only valid entries.
6. Saves an audit artifact and candidate shortlist; does not call Meta POST.

## Safety
Official corrections, precise application time, job-unit restrictions, profile destination and the next IMAGE-turn media asset must all be verified. Missing approved entries cannot be converted to ready by the runner. The stage file may be empty, in which case the queue is unchanged and the existing publisher warning remains active. Never retry an ambiguous Meta POST. Real publication success requires a Threads ID, public URL, and GET verification.

## Validation
Run: python -m unittest discover -s tests -p 'test_threads_*.py' -v
Do not merge until repository checks pass.
