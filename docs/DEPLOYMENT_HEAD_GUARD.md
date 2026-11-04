# Preserve newer content at deployment time

Manual exact-SHA deployment and scheduled publication now recheck remote main before publication. A manual build also checks at the start. If a blog or data update advances main during a queued build, the old checkout fails without replacing the existing site. The check does not modify data, push state, Threads or secrets. Scheduled data commits keep their existing fast-forward push protection; the final check uses the resulting actual checkout SHA.

The guard is reused from the integrated SupportPick work after an actual newer blog update overtook an older approved manual run. An isolated git integration test advances remote main, proves the stale checkout is rejected, then proves the rebuilt current checkout is accepted. Deliberate rollback should revert the relevant change on current main rather than publishing a stale checkout over newer content.
