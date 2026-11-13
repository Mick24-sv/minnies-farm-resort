# Customer arrival and departure times

The room booking form now accepts both times at minute precision in Philippine time (UTC+8). The server validates them and stores them on the reservation. Confirmations, My Bookings, and the staff booking table display the saved values. Staff room walk-ins also accept both times. Rates remain per night; departure must be on a later date.

## Activate in Supabase

The migration was applied on November 14, 2026 to project `yrmmuuaomglqoevooyxu` through Supabase MCP. Both time columns, the validated constraint, and server-only function permissions were verified. Local `.env` now enables `BOOKING_TIMES_ENABLED=1`; restart any running local server to load it. Existing booking records were preserved, and no live test bookings or payments were created. Hosted server environments still require the flag and a redeployment.

1. For another project, run [20261114_booking_times.sql](../../database/migrations/20261114_booking_times.sql) in the correct project's Supabase SQL Editor using a database administrator session, or apply it through Supabase MCP. Do not share database passwords or service keys in chat.
2. Confirm the `bookings` table has `check_in_time` and `check_out_time`, and `resort_create_booking_with_times(jsonb)` exists. The migration reloads the PostgREST schema cache.
3. Set `BOOKING_TIMES_ENABLED=1` in the server environment (`.env` locally and the hosting environment for deployment), then restart or redeploy Flask. Keep this setting server-side.
4. Confirm `/api/payment-options` reports `booking_times_enabled: true`. The room form's Arrival time and Departure time controls should now be enabled. Verify a reservation in a dedicated test account before relying on the live flow.

Until activation, those controls show an unavailable message and the existing date-based booking flow remains available. The API rejects supplied times when the capability is disabled instead of silently dropping them. If rolling back the application flag, restart the server; retain the nullable columns to preserve saved times.

## Data and availability

- Existing reservations retain null time fields and display “Time not specified.” No arrival or departure values are invented.
- The new server-only function wraps the existing booking function in the same transaction, preserving its pricing, guest authorization, payment, and retry behavior. A conflict rolls back the booking and any payment record.
- A room lock serializes new time-aware reservations. The wrapper additionally rejects overlapping timestamp ranges, including an arrival before the previous guest's departure on the same day. An arrival exactly at a known departure is allowed by this check, subject to the existing booking function's availability rules.
- Reservations without recorded times conservatively occupy their entire boundary days for this additional overlap check. A new same-day turnover against such a reservation can be rejected until its actual times are known. This migration does not rewrite historical reservations or replace the existing date-based availability rules.
- Browser database roles cannot execute the new function; only the backend's service role can. Existing RLS policies are unchanged.

## Verification

Run `python -m unittest discover -s tests/backend -p "test_*.py" -v` and `node tests/frontend/structure-check.cjs`. The browser suite in [tests](../../tests/README.md) covers choosing both times, the actual submitted JSON, confirmation and booking-list displays, and disabled controls before activation. All browser API responses are mocked.

`tests/database/booking-times.cjs` executes the actual migration against an isolated PostgreSQL engine through PGlite. Set `PGLITE_PATH` to an installed `@electric-sql/pglite` module and run `node tests/database/booking-times.cjs`. It verifies storage, legacy rows, retry conflicts, overlap rollback, exact turnover, function permissions, and reapplication. The original booking function is stubbed in that isolated test; live database triggers and pricing are not exercised.
