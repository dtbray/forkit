# WordPress category imports

Import all recipe-bearing posts assigned to a WordPress category without scraping search-result layouts or sending pages to an LLM:

```bash
python -m forkit.wordpress https://www.budgetbytes.com/category/recipes/vegetarian/
```

Run inside the application container, where the database and persistent `/data` volume are already configured. The main database must have migrations applied. Any public WordPress installation with the standard category and post endpoints can be used. The category URL is resolved to its exact taxonomy ID; links must remain on the configured origin. Recipe source URLs remain attached to every saved recipe.

The importer fetches robots.txt using an identifying Forkit user agent and honors disallowed paths and crawl delays. It enumerates posts in ID order, 100 at a time, using WordPress pagination headers. Each fetched page and its discovery checkpoint commit together. A manifest snapshots the category membership for that run; a later refresh reconciles newly published posts. Concurrent site changes can affect offset-based pagination, so a refresh is needed before treating a long-running manifest as permanently exhaustive.

Recipe requests are sequential, five seconds apart by default (minimum two seconds). HTTP 429 and transient failures trigger bounded exponential backoff and Retry-After handling; publisher access denials or repeated failures pause the run. Requests use the existing SSRF protections. Pages are compressed and cached by post ID plus modification timestamp. Imports require Recipe JSON-LD with ingredients and instructions; collection pages and incomplete recipes are recorded as skipped. Images are downloaded with the same pacing as recipe pages, sanitized into local WebP variants, and attached without modifying recipe text. Existing recipes receive photos from their cached JSON-LD pages before pending imports resume; cached pages from other categories on the same site are reused. Photo failures are checkpointed independently and do not discard a saved recipe. No AI credentials are needed.

State, compressed pages, per-item errors and atomic progress snapshots live under `/data/imports/<source-hash>/`. Recipe commits are checked on resume, including recovery when a process stops between saving a recipe and recording its checkpoint. A per-source process lock prevents duplicate workers. Existing recipes and user edits are retained.

Options:

- `--no-images`: skip the photo backfill and downloads for a text-only run.
- `--limit 5`: process up to five pending candidates, useful for a canary.
- `--refresh`: re-enumerate category metadata; unchanged recipes are not fetched again.
- `--retry-failed`: retry recorded failures using cached pages when available.
- `--delay 5`: request spacing in seconds, raised to any applicable robots crawl delay.
- `--interval 86400`: remain running, then refresh daily after the preceding run finishes. Pause/error states also wait this interval before retrying.

Changed source posts whose recipes are already saved are flagged as `changed` for review; they do not overwrite stored ingredients, notes or ratings. Automatic update application and automatic deletion when posts leave the category are intentionally not provided. A refresh polls the lightweight category API; subscribing to RSS is not required for this importer and RSS is not used for the initial backfill.

The read-only `/api/imports` endpoint and Library progress panel show saved, pending, skipped, failed and changed counts. The Library polls every three seconds while visible and refreshes recipe results when progress changes, preserving search filters and pagination. Requests do not overlap; hidden tabs pause polling, and failed requests retain the last counts with a reconnecting indicator. A Refresh now action remains available. Pagination lets the Library browse beyond its first 50 recipes. To inspect recorded errors, query the source's `state.sqlite` items table. Pause safely by stopping the importer service; restart it to resume. Do not delete the state directory to retry a job.

The lab deployment is declared in homelab `ops/forkit/compose.yml`. Its worker shares only the application's persistent data and has a separate CPU/memory budget. Back up both the recipe database and `/data/imports` to preserve recipe content, provenance and resumability together.


The navigation's Color theme selector offers System, Light and Dark. System follows the OS color preference automatically; manual choices persist in local storage. The saved theme is applied before styles paint to avoid a light flash, and CSS overrides cover cards, forms, recipe details and cooking views. Storage restrictions do not prevent changing the current theme.
