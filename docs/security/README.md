# Security hardening — November 14, 2026

These are local source changes. They protect the hosted application only after deployment. No live accounts, payments, environment secrets, or database privileges were changed.

That statement describes the initial hardening review. A later [explicitly authorized repair](account-repair.md) converted two legacy password fields to hashes and verified real staff/guest login. No database-permission SQL has been applied.

## Implemented

- Removed plaintext-password authentication fallback. Accounts containing plaintext passwords must use password reset; their plaintext value will no longer authenticate.
- New and reset passwords require 12–256 characters and use salted PBKDF2-SHA256 with 600,000 iterations. Existing valid PBKDF2 hashes still authenticate.
- Google access tokens must belong to this application's OAuth client before Google identity information is accepted.
- Tokens have an explicit 15-minute lifetime, are accepted only in authorization headers, and are stored in tab-scoped `sessionStorage` rather than persistent `localStorage`. Previous persistent tokens are removed, so users must sign in again once.
- Uploads require a verified staff identity and accept only bounded JPG/PNG/WebP data with matching file signatures.
- Staff/guest checks protect inventory and money-recording actions. Booking ownership is enforced before private details are returned. Reviews require the user's own completed booking.
- Public room, service, review and account responses use field allowlists. Public review output no longer exposes internal user/booking IDs or nested account objects.
- Login/registration query values are encoded; review IDs, authentication inputs, JSON object shape and body size are validated. Inventory creation accepts only named fields.
- CORS is restricted to configured frontend origins and localhost. Cross-origin mutations from other browser origins are rejected. This is additional browser protection, not a substitute for authentication.
- API errors no longer return internal exception text. Health checks no longer advertise configuration details. API responses use `private, no-store`.
- Added anti-framing, MIME-sniffing, referrer and permission headers. HTTPS responses use HSTS. Equivalent headers are included in Vercel configuration for static pages.
- The direct Python entrypoint binds only to localhost with the interactive debugger disabled.
- Added a baseline CSP blocking plugins, foreign base URLs, external form actions and framing. This is **not a strict XSS policy**: the current Vue runtime compiles templates, and the app still uses inline scripts/styles. A compiled frontend and stronger script policy would be a separate change.
- Four pinned Vue/GSAP/DrawSVG/Lenis CDN scripts have SHA-384 integrity checks. Removed the unused Facebook SDK; social share links do not need it.
- Added bounded per-worker request limits: 12 authentication POSTs/minute and 240 other API requests/minute per observed client address. Arbitrary forwarding headers are not trusted.
- Updated dependency pins and consolidated backend requirements through the root `requirements.txt`. The updated stack requires Python 3.10 or newer.

## Verification

- 22 backend/profile/security tests passed, with mocked database writes and no emails.
- The 12-group browser regression suite passed on updated dependencies with mocked account/payment APIs.
- Asset references and JavaScript syntax passed.
- `pip check` passed.
- After removing the unused SendGrid SDK during cleanup, `pip-audit` reported no known vulnerabilities in the 18 resolved runtime packages. See [the machine-readable audit](dependency-audit.json). This is a known-advisory check, not a guarantee that every dependency is safe.
- No configured Supabase, JWT or email secret values were found in the frontend text assets. `.env` is not tracked and was not found in available Git history.
- A subsequent cleanup review confirmed the **current Supabase service-role key is present in old versions of `api/index.py` in two commits**. Absence of `.env` from history does not mean the key was never committed. See [the exposure review](../deployment/github-push-review.md). Rotate/revoke this credential before sharing or deploying the repository history.
- The configured JWT secret meets the 32-character length check. The Supabase backend key identifies as `service_role`; it must remain server-only. Actual secrets were not printed or modified.

Run the tests from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests/backend -p "test_*.py" -v
node tests/frontend/structure-check.cjs
```

## Production work still required

1. **Deploy these source changes.** Keep `DEBUG=0` in production. Configure `FRONTEND_URL` with the real HTTPS URL. Add `ALLOWED_ORIGINS` only when an additional frontend origin needs access. The Google client ID in server configuration must match the frontend and Google's authorized JavaScript origins.
2. **Review and apply database permissions in a sandbox first.** [The prepared SQL](../../database/security/restrict_browser_access.sql) enables RLS, revokes browser-role access to application tables and `resort_` functions, and retains server service-role access. It has **not** been applied because live database access was restricted to read-only. Audit any other privileged database functions and policies separately.
3. **Add shared or edge rate limits.** The local limiter resets when a process restarts and is not a deployment-wide defense on Vercel. Configure the hosting WAF or a shared rate-limit service, with correctly trusted client-address handling. No hosting firewall configuration was changed here.
4. **Plan server-side session revocation.** Logout currently removes the browser token but does not revoke a copied JWT. A copied token can remain valid until its 15-minute expiry; password resets do not revoke already-issued tokens. Persistent revocation storage or a server-managed session design is needed to change this.
5. **Consider HttpOnly cookies with CSRF protection.** Tab storage reduces persistence but remains accessible to JavaScript. It does not defeat XSS. Do not move tokens to cookies without adding the corresponding CSRF and cross-origin controls.
6. **Continue live integration and device testing.** Successful Google OAuth, real profile saves, payment verification and email delivery were not tested against real accounts in this review. Use dedicated test accounts and a sandbox. Backups, key rotation, monitoring and administrator MFA must be configured in the hosting/Supabase accounts.

API paths and public OAuth client IDs are visible by design. Never place the Supabase service key, JWT signing secret, passwords or email-provider key in `public/` or frontend code.

Implementation guidance: [Flask security considerations](https://flask.palletsprojects.com/en/stable/web-security/) and [JWT revocation guidance](https://flask-jwt-extended.readthedocs.io/en/stable/blocklist_and_token_revoking.html).
