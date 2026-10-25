# Before pushing to GitHub

The exposure check found the current Supabase service-role key in earlier commits `193c1cd5`, `048ccfdd`, and `003eb5fc`, in historical versions of `api/index.py`. The key value is intentionally not reproduced here.

Rotate/revoke that privileged credential in Supabase before publishing the history. Update the replacement `SUPABASE_KEY` in your local `.env` and Vercel environment, and redeploy. Revoke the old credential; deleting it from the newest file does not invalidate it. Never paste a replacement key into a tracked file.

The current `.env` is ignored and untracked. The current working files did not contain the configured secrets or common secret-token patterns during the scan. Public OAuth client IDs are expected in browser code; they are not client secrets.

No Git history was rewritten and no push was performed. If the repository was already public, treat the exposed key as compromised even after history cleanup. Cleaning published history affects collaborators and should be planned separately.

Changes made during this review: additional ignores for private-key/credential files and logs; removal of password hashes from account responses; Google token verification on the backend instead of trusting browser email fields; removal of response-body logging that could contain user data; and removal of the known JWT signing-secret fallback. Configure `JWT_SECRET_KEY` in Vercel before deployment.

Local tests cover those authentication protections and static-file boundaries. This is a focused exposure review, not a full security audit or a guarantee that the complete application is free of vulnerabilities.
