# Hide and restore customer history

Guests can hide their own completed or cancelled room reservations and service requests. Pending or confirmed items cannot be hidden. Reservation history has Upcoming, Past, and Hidden filters; service requests have Requests and Hidden filters. Choose Restore to history inside Hidden to return an item to its normal list. Payment history and receipt access remain available while hidden.

Preferences persist in Supabase across devices through `customer_history_visibility`, independently of transaction rows. Staff lists ignore customer preferences. No booking, service, payment, or receipt record is deleted or edited by hiding or restoring. If a previously hidden item becomes active, the UI shows it again rather than concealing an active transaction.

Applied `database/migrations/20261114_customer_history_visibility.sql` to the connected Supabase project on November 14, 2026. RLS and revoked browser permissions protect the preference table. The server-only function locks the target row and validates the authenticated customer, ownership, current status, and entity type. The API obtains the actor from the login token; body-supplied identities are ignored. Restoring deletes only the corresponding hide preference. Repeating hide or restore is safe.

The migration adds storage and a function; existing customer records and preferences were not changed. Deploy the updated Flask and public files to enable the interface on the hosted website. No new environment variable is required.

Verified with 51 backend tests, an isolated PostgreSQL test (`tests/database/history-visibility.cjs`, using `PGLITE_PATH`), and a mobile browser test (`tests/frontend/history-smoke.cjs`, using `PLAYWRIGHT_PATH`). Browser responses are mocked; no live customer history was hidden during verification.
