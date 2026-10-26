# Saved recipe controls

Recipe details persist favorites, personal notes and ratings through
`PATCH /api/recipes/{id}`. The supported fields are `favorite` (boolean),
`user_notes` (text or null, at most 100,000 characters), and `rating` (1–5 or
null). Unknown fields and invalid values return 422. Favorites are independent
of ratings. The page acknowledges successful saves, retains unsaved notes on
failure, and provides a Save notes button for retrying. Recipe API reads bypass
the service worker cache so a reload cannot restore stale personal edits. The
static app shell explicitly disables server rendering; API requests run in the
browser in both preview and the deployed container.

`DELETE /api/recipes/{id}` removes the recipe, ingredient rows, search index and
tag associations. Feed references are cleared and dismissed. An exact source
URL tombstone prevents the background importer from recreating explicitly
deleted recipes, including after its checkpoint manifest is rebuilt. Reimporting
that URL returns 409 `previously_deleted`. There is no UI to clear a deletion
marker yet. Downloaded image files remain available to existing clients and are
retained in the data volume; deletion is not a disk reclamation operation.

Apply migrations through revision 0005 before starting the updated app or worker.
The migration preserves existing notes and ratings and initializes explicit
favorites to false; earlier favorite button clicks did not persist a value.

Library search accepts ordinary words, combines them with AND, and treats FTS
operators and punctuation as input rather than an executable query language.
Punctuation-only searches return an empty result. Search is capped at 500
characters; pages accept limits of 1–200 and nonnegative offsets. `favorite`
filters either saved state, `tag` selects a tag, and `source` selects an exact
hostname such as `www.budgetbytes.com`. Results have a stable ID tie breaker.
