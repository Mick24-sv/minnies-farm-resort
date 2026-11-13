# Email delivery

The active Flask backend now uses SendGrid for password-reset emails and the same transaction updates shown in the notification inbox. Each guest/staff notification produces a separate email for that account. No screenshots, receiving account numbers, or payment references are added to emails.

## Activate

1. Run `database/migrations/20261025_email_delivery.sql` in Supabase SQL Editor, after `20261025_notifications.sql` and the payment/counter migrations.
2. Configure these environment variables in `.env` locally and in Vercel for production:

   ```env
   SENDGRID_API_KEY=YOUR_SENDGRID_API_KEY
   FROM_EMAIL=YOUR_VERIFIED_SENDER_EMAIL
   FRONTEND_URL=http://localhost:5000/
   ```

3. Restart Flask. Before deploying, change `FRONTEND_URL` to the actual public HTTPS website address and redeploy. A localhost link opens the recipient's own computer, so it is only suitable for local testing.
4. Use **Forgot password** with your registered account, or create a new transaction update. Check your inbox and spam folder. The backend does not send test emails automatically during development checks.

The new queue covers future notifications only. Historical notifications will not produce a batch of old emails.

## Delivery behavior

Requests process at most one queued email after a successful API POST or authenticated notification poll. Reset emails take priority. This runs before the response finishes, without a background thread that could be interrupted by serverless shutdown. Sending can add several seconds to a request. There is no independent scheduled worker: pending mail continues when the app receives these requests, including the existing 30-second notification polling. If nobody is using the app, queued transaction messages wait until activity resumes.

Booking/payment success is independent of SendGrid success. The stored email queue tracks attempts and provider acceptance. HTTP 202 means SendGrid accepted the email, not that it reached the inbox. See the [Mail Send API](https://www.twilio.com/docs/sendgrid/api-reference/mail-send/mail-send).

Rate limits and provider server errors are retried after five minutes, with a maximum of five attempts. Rejected requests (such as invalid sender or exhausted credits) become `failed`; fix the provider account before retrying them. Network errors or abandoned workers become `uncertain` to avoid automatically sending the same message twice. Check SendGrid Email Activity before manually retrying an uncertain job.

Inspect status in Supabase SQL Editor:

```sql
SELECT id, kind, status, attempts, last_error, created_at, accepted_at
FROM public.resort_email_outbox
ORDER BY id DESC LIMIT 50;
```

After fixing a known failure, retry a specific transaction email:

```sql
UPDATE public.resort_email_outbox
SET status='pending', attempts=0, next_attempt_at=now(), lease_token=NULL
WHERE id=YOUR_JOB_ID AND kind='transaction' AND status='failed';
```

For a failed reset email, request a new reset link instead. Reset links expire after one hour and work once. Tokens are consumed atomically in the database, which supports separate Vercel instances. Only a hash is stored in the reset-token table; the private email queue necessarily holds the link until delivery. Reset requests for the same account are limited to one per minute. The endpoint returns the same response for known and unknown addresses.

## Local verification

Run `python -m unittest discover -s tests`. These tests mock SendGrid and database RPCs: they verify message formatting, isolated recipients, failure handling, reset-token hashing, and the active Flask route registration. They do not execute PostgreSQL migrations or deliver real email. Test the migration and a real reset link on a test account after activation.
