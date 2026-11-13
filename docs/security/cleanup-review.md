# File and Supabase cleanup review

Reviewed November 14, 2026. Supabase access remained read-only; no live rows, tables, functions, policies or credentials were changed.

## Removed locally

- `api/legacy/`: 11 tracked files from an earlier backend, explicitly documented as not loaded by the running app. They remain recoverable from Git history.
- `examples/stillwell-booking/outputs/site.tar.gz`: an old generated deployment package. The demo's source, nested repository and Sites identity are preserved.
- Four generated `__pycache__/` directories under `api/` and `tests/`. Python may regenerate these during normal use.
- Empty root `.openai/` and demo `outputs/` directories.
- The unused SendGrid Python SDK requirement. The active email delivery module calls SendGrid through `requests`; email functionality and configuration remain.

Kept the active backend, frontend features, payment QR images, examples requested in this session, tests, documentation, `.env`, and the isolated `.venv` used to run the system.

## Supabase findings

All 19 exposed application RPC names appear in the active backend. All 12 application tables have a known operational purpose:

| Tables | Purpose |
| --- | --- |
| `users` | Account identity and authentication |
| `rooms`, `services` | Inventory and pricing |
| `bookings`, `service_avails` | Reservation and service-request history |
| `booking_payments`, `service_payments` | Payment ledgers |
| `resort_transfer_references` | Shared transfer-reference tracking and duplicate protection |
| `resort_password_resets` | Password reset token lifecycle |
| `resort_email_outbox` | Queued email delivery and retries |
| `resort_notifications` | Private transaction notifications |
| `reviews` | Guest reviews |

Some tables are accessed through database functions rather than by name in Python. An absent direct Python reference does not make them unused. Row counts alone cannot establish that records are disposable. No database item was identified as safe to remove without examining retention rules and database-side dependencies.

## Important credential finding

The current Supabase service-role key was found in historical versions of `api/index.py` at commits `048ccfdd` and `003eb5fc`. Its value was not printed or added to this report. Removing obsolete files does not revoke an exposed credential. Rotate/revoke that key in Supabase, replace it in local and hosted environment settings, and redeploy. See [the exposure review](../deployment/github-push-review.md).

## Validation

After removing the unused code/dependency, all 22 backend/profile/security tests and the frontend asset/syntax check passed. `pip check` found no dependency conflicts. The runtime vulnerability report was refreshed after the requirement change; see [the audit](dependency-audit.json).
