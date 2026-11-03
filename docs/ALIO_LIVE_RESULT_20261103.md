# ALIO live verification result — 2026-11-03
Code HEAD tested: 8bbd92cbc259cc4062b348fe2848724f8056a8d7
Run: https://github.com/kllollain-max/careerpick/actions/runs/41572738711
Job: 125709180997 — success.
Artifact: 13202127273, alio-isolated-live-check, expires 2026-11-06T03:32:29Z.
Digest: sha256:b0658c74d8d7dd8f3f5b804dc817110274a923e605c621e38c687403d10ac856

- Key present in GitHub runner, never printed or exported.
- Official POST/query list and separate detail identity verification succeeded.
- Full isolated collection succeeded at 2026-11-03T12:32:01+09:00.
- Candidate: before 520, after 610; added 90, changed existing card records 0, removed 0.
- Deadline-expired in retained candidate: 97, date-based only. This is not a newly closed delta or verification of early closure.
- Repository source snapshots remain unchanged (520 cards); candidate pair is in the private artifact, not deployed or committed as live site data.
- Source hashes: alio.json 8aa63adf95f679d3fba235fe572c40bed8794f6dc435bb55a16fbaf8df1b3e79; alio-detail.json b56eb9918628899fbf4bd98f8f04468fada5d59634cf97e2ca0eb8012738fd1a.
- CI: 3 contract tests and existing partial-fetch guard passed. Original homepage checks were not repeated because static source/data remain unchanged.
- No main merge, public visibility change, Pages activation, deployment or scheduled collection.
- Initial live check rejected observed resultCode=200 versus Swagger example=0. Adapter now accepts 0/200 with strict list count/shape and detail ID checks.
