# History query performance

The agent database owns message counts, timestamps, roles and compression
lineage. History projections remain read-only and preserve those values.

Large tool/image rows made the messages join expensive even when the UI
requested only metadata. With the covering indexes installed by
`scripts/ensure_state_db_read_indexes.py`, importable-session projections use
indexed scalar counts and latest timestamps without fetching message bodies.
Databases with missing, partial or incompatible role indexes keep the existing
join fallback. The request path never installs indexes.

Install read indexes only in a drained maintenance window, after a database
backup, following that script's `--confirm-drained` requirements. This is
independent of the WebUI session index and does not delete history.

Unchanged idle sidebar projections remain cached for 15 seconds. Source
fingerprints, settings changes and explicit profile-scoped mutation invalidation
still apply on every request. Streaming retains its 45-second cache policy and
live runtime overlay.

Shell URLs and the service worker use a digest of the static JS, CSS and HTML
alongside the release version. Local Docker builds whose release version is
`unknown` therefore invalidate stale shell assets when their content changes.
Legacy `v=unknown` asset URLs revalidate instead of receiving immutable caching.
Request-duration logs use a monotonic timer to survive system clock adjustments.

Validation: `./scripts/test.sh tests/test_history_covering_reads.py
tests/test_pr7445_readonly_review_followups.py
tests/test_state_db_readonly_readers.py tests/test_session_sidebar_cache.py
tests/test_session_metadata_cli_lookup.py
tests/test_static_asset_compression_and_cache.py`.


All-profile cache validation reuses committed fingerprints already read during
context enumeration, retaining home/profile identity and excluding SHM reader
locks. Cache lookup returns its stale reason from the same validation read.
The browser bundle release stamp remains the release version used by the
stale-client monitor; asset URLs use the separate content digest.
