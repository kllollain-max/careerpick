# API snapshot selection policy
- This is an offline adapter for an **already verified** normalized JSON snapshot, not a live API client.
- Required keys: id, official_url, official_verified (true after independent review), application_deadline (YYYY-MM-DD HH:MM, KST), employment_type (exactly 정규직), headcount (positive integer).
- Missing or date-only deadlines are held, not treated as active. ALIO posting end date must never be substituted for the application deadline.
- Mixed employment types are held unless an independently verified per-role regular headcount is supplied as its own record.
- Select by regular employment then descending headcount; measured popularity ranking is unavailable and not claimed.
- Reject elapsed deadlines, preserve existing outputs, never auto-post.
- The currently published CareerPick ALIO pages do not consistently contain confirmed application deadlines, so most cannot pass this gate without official notice verification.
- Existing collector, site, Threads workflows, and production branch must remain unchanged.
