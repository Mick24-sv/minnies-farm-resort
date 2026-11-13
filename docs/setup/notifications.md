# Transaction notifications

## Five-month retention

Applied `database/migrations/20261114_notification_retention.sql` to the connected Supabase project on November 14, 2026. Notifications expire after five calendar months, calculated in Philippine time. Expired items are excluded from every inbox page and unread count immediately on the next fetch, including unread items. A server-side pg_cron job named `resort_notification_retention` deletes expired notifications daily at 03:00 Philippine time (19:00 UTC), even when the site is closed. No frontend redeployment or environment flag is required.

Only notification rows are deleted. Related delivery records retain their rows with a null notification reference; reservations, payments, and account records are preserved. Browser roles cannot call the purge function. The scheduled job was verified active, and the initial purge found no expired notifications.

Run the isolated database test with `PGLITE_PATH` pointing to an installed `@electric-sql/pglite`, then `node tests/database/notification-retention.cjs`. It checks the exact cutoff, unread count, ownership, pagination, deletion, delivery preservation, and permissions. Cron scheduling is verified separately against Supabase.

## Notification behavior

Run `database/migrations/20261025_notifications.sql` in the Supabase SQL Editor after the booking payment, service payment, and service counter migrations. Restart Flask and refresh the browser. No new environment variables are needed.

Signed-in staff and guests have a notification bell beside the navigation. The inbox shows an unread count, transaction details, dates in Philippine time, mark-read controls, and older updates. Opening an update opens that specific room reservation or service request, with the same ownership checks as the payment screens. It does not change a transaction's payment status.

Notifications are created in the same database transaction as the underlying change. They cover new requests, payment submissions, verified receipts, rejected submissions, counter payment choices, confirmations, cancellations (including expired holds), and completed transactions. New events go to the owning guest, when present, and each staff account. Walk-ins without a guest login only notify staff. Existing transactions do not generate a backlog when this migration runs. Saving the same counter choice again or retrying an unchanged transaction creates no extra update.

The active site checks for updates every 30 seconds, pauses polling in hidden tabs, and refreshes the visible dashboard when a new event arrives. Unpaid holds expire on the next applicable API request, including notification polling. There is no background scheduler: a closed site receives the stored updates when the user returns. These are in-app notifications; no email, SMS, or browser push is sent.

Notifications are private per user. Tables have RLS enabled and direct public access revoked; only the backend service role can execute the read/list functions. The backend derives the recipient from the authenticated token, never from a client-supplied user ID. A notification contains transaction references and status information, without screenshots, receiving account numbers, or transfer references.

Before deploying, run the migration in a test Supabase project and check with separate staff and guest accounts: create a request, submit a transfer, verify/reject it, choose counter payment, cancel, complete, and let a hold expire. Confirm an unrelated guest cannot see or mark another user's updates. Local HTTP and UI tests use mocked data; they do not execute PostgreSQL triggers.
