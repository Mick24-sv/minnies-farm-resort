# Authorized legacy-password repair

Completed November 14, 2026 after explicit approval to update the two incompatible password fields. The earlier read-only rule continues to apply to unrelated database work.

- All eight accounts remained present: one staff and seven guests.
- One staff and one guest account used a legacy plaintext password format rejected by hardened login.
- Updated only those two password fields to salted PBKDF2-SHA256 hashes with 600,000 iterations. Existing login passwords, identities and roles were preserved.
- Verified the other six stored password values were unchanged.
- The real Flask login and authenticated identity routes returned success for both repaired accounts.
- A browser accepted the real staff credentials, displayed the post-login animation, and opened Staff Dashboard. Dashboard data was mocked to avoid hold-expiration, payment, notification or email side effects.
- No passwords, hashes, access tokens or email addresses were saved to files or printed. No bookings, payments, account roles or schema permissions were changed. Queued email delivery was disabled for verification only; persistent environment settings were unchanged.

The repair utility is `scripts/migrate_legacy_passwords.py`. It defaults to read-only dry-run, rejects known hash formats, and stops on unexpected account counts/roles. Applying it again with no legacy accounts makes no changes. Do not use it for unrelated account maintenance or while account password changes are being performed concurrently.
