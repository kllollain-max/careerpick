Title: Restore CareerPick from preserved snapshots under /careerpick/

Draft only; no merge/deployment authorization.
수정 담당: ChatGPT/Codex
검토 담당: 운영자 지정 대기

Restores the original website and 520 ALIO snapshot notices. Reuses search, filters, matched conditions, saved notices and application tracking. The build scopes local and canonical links to `/careerpick/` while preserving calendar separators and external URL classification. PWA caches are isolated from sibling projects.

Only allowlisted static output enters `dist/`. The active workflow is manual verification only; collector and Pages workflow proposals remain inert outside `.github/workflows`.

Validation: 48 homepage tests, 27 detail tests, 6 expiry-schema tests, 3 collector preservation tests, sitemap regression and original partial-fetch guard pass. 373 generated JavaScript units parse. 27,580 internal links have no missing target. Cloud-browser search/filter/reset, matched-condition save, saved notice persistence/removal, application status persistence, modal, standalone detail/direct reload checked. List and detail iframe widths 320/390/1440 have no horizontal overflow/broken images. Browser extension metadata errors are excluded from site errors. One official ALIO notice checked; full live reception/attachment verification remains incomplete.

Blocks: ALIO_KEY/live API contract and manual collection not verified. Draft PR pending branch upload. GitHub Pages not enabled; no publishing or existing automation changes.
