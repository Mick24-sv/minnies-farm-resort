# Added-feature verification

Checked November 14, 2026 in headless Microsoft Edge against the local Flask server.

After the file-structure reorganization on the same date, all 12 browser groups and four backend tests passed again. The structure check also confirmed 23 local HTML asset references, six feature scripts loaded before `app.js`, valid JavaScript syntax, and the relocated example path. Vercel's `public/` output and `api/index.py` entrypoint are unchanged.

After security hardening, the updated dependency stack passed 22 backend/profile/security tests and the same 12 browser groups. See [the security report](../security/README.md) for the dependency audit, security-specific coverage, and remaining deployment requirements.

## Results

All 12 browser test groups passed, with no uncaught browser errors:

| Feature | Verified |
| --- | --- |
| Libraries | Vue, GSAP, DrawSVG and Lenis load |
| Staff revenue | Peso formatting; 3, 6 and 12 chart columns |
| Rating card | Counts to 4.8; fifth star reaches 80%; five breakdown rows |
| Profile | Dirty save bar, Discard, failed save retains edits, successful save clears dirty state |
| Payment confirmation | DrawSVG sequence mounts and completes; eight ticks; pulse fades |
| Sticky navigation | Lenis reaches the section with header offset; active pill updates |
| Tour | One spotlight; Next, Back and Escape |
| Footer | Reveals at scroll end; links become accessible; social hover and pressed states |
| Mobile tabs | Tab navigation and indicator placement |
| Pull to refresh | Touch gesture triggers a new booking fetch; pull panel resets |
| Login | Successful email-login response triggers the logo animation before dashboard navigation |
| Separate session demo | Date/time selection, summary, delete dialog, outside click and cancel |

Four Flask profile API tests also passed: authentication required; invalid/privileged fields rejected; only the authenticated user's name updated; failed database updates reported. All JavaScript files passed syntax checks.

## Limits

### Additional live read-only checks

Also checked November 14, 2026 using the existing `.env`, with no account changes or payment entries:

- Live Supabase reads of rooms, services, users and bookings returned HTTP 200. No personal records or credentials were printed.
- The live database schema exposes all 13 booking/service payment RPCs referenced by the application. The RPCs were not invoked.
- `/api/payment-options` returned HTTP 200 with GCash and bank-transfer options. Both QR assets loaded. This checks configuration and assets, not payment settlement.
- Unauthenticated profile updates and missing/invalid Google tokens returned HTTP 401.
- A signed-out Edge browser loaded real room/service data: four rooms were displayed; payment-options, services and rooms APIs all returned HTTP 200.
- Desktop section navigation, the tour and mobile room navigation worked with live public data, with no uncaught browser errors.
- The signed-out browser check blocked every non-GET local API request. It performed no database writes.

### Remaining limits

- Browser account, booking, service and payment responses were mocked. No database records were changed.
- Profile API tests mocked database access. They exercise Flask routing, JWT authentication and validation, but do not prove a live Supabase write succeeds.
- Successful interactive Google OAuth, actual payment workflows, email delivery and live profile writes still need integration checks using a sandbox or dedicated test account. The current user requested read-only checks on the live database.
- Revenue and rating cards intentionally use sample data.
- `examples/stillwell-booking/dist/index.html` is a separate demo. Its session booking and delete dialog are not part of the resort app and perform no real reservation or deletion.
- Mobile checks used a narrow desktop viewport and simulated touch events. Physical-device behavior still needs checking.
- Automated style and state checks do not replace a visual review of animation quality.

## Repeat the checks

Start Flask from the repository root. On this computer Python is installed but absent from PATH:

```powershell
& "$env:LOCALAPPDATA/Programs/Python/Python313/python.exe" -m flask --app api.index run --host 127.0.0.1 --port 5000 --no-reload
```

In another terminal:

```powershell
& "$env:LOCALAPPDATA/Programs/Python/Python313/python.exe" -m unittest discover -s tests/backend -p test_profile_api.py -v
```

The browser suite requires an installed `playwright` or `playwright-core` package and Microsoft Edge. Set `PLAYWRIGHT_PATH` to the installed module directory, or install Playwright in your chosen development environment, then run:

```powershell
node tests/frontend/features-smoke.cjs
```

The browser suite intercepts localhost API calls and uses dummy accounts. It does not require real login credentials.
