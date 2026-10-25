# Minnie's Farm Resort — Website (Vue + Flask on Vercel + Supabase)

Hi, I'm Mick — a full-stack developer focused on building practical web apps for real businesses. I design and develop modern booking systems, customer-facing interfaces, and backend services that make operations smoother and more efficient.

This repository contains the **Minnie's Farm Resort** room booking website.

- **Frontend:** Static HTML/CSS + Vue (loaded via `public/index.html`, logic in `public/assets/js/app.js`)
- **Backend API:** Flask app deployed as a Vercel Serverless Function (`api/index.py`)
- **Database:** Supabase (PostgREST)

## How the app works

### Frontend (client)
The UI is a single-page experience controlled by Vue state.

- `public/index.html` defines the page structure (Home, Rooms, Room Detail, Services, Dashboards, modals).
- `public/assets/js/app.js` holds the Vue app state and calls the backend API using `fetch()`.
- `public/assets/css/style.css` provides the styling and responsive layout.

The frontend talks to the backend via `API_URL`.

- In local development, the API is typically `http://localhost:5000/api`.
- On Vercel, the API is typically `/api`.

### Backend API (server)
The backend is a Flask API located in `api/index.py`.

It:
- Validates requests and authorization tokens
- Calls Supabase via REST endpoints (PostgREST)
- Returns JSON responses to the frontend

Key endpoints (high level):
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET  /api/auth/me`
- `POST /api/auth/forgot-password`
- `POST /api/auth/reset-password`
- `GET/POST/PUT/DELETE /api/rooms` and `/api/rooms/<id>`
- `GET/POST /api/bookings` and booking status management endpoints
- `GET/POST/PUT/DELETE /api/services` and service request endpoints
- `GET/POST /api/reviews`

### Database (Supabase)
Supabase is used as the data store.

Tables include (names may vary depending on your Supabase project):
- `users`
- `rooms`
- `bookings`
- `services`
- `service_avails`
- `reviews`

The backend uses `SUPABASE_URL` and `SUPABASE_KEY` to communicate with Supabase.

## Deployment (Vercel)

For manual deposits, payment verification, and walk-in counter bookings, follow [payment setup](docs/payment-setup.md), including the required SQL migration and receiving-account environment variables.
This repo is designed to deploy to Vercel.

- Requests to `/api/*` are routed to the Flask serverless function (`api/index.py`).
- All other routes serve the static frontend.

## Local development

### 1) Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2) Set environment variables
Copy `.env.example` to `.env` in the project root, then replace the placeholder values (this repo ignores `.env` via `.gitignore`).

```powershell
Copy-Item .env.example .env
```

Required variables:
- `SUPABASE_URL` — your Supabase project URL
- `SUPABASE_KEY` — your Supabase API key
- `JWT_SECRET_KEY` — a strong secret string used to sign JWTs

Optional:
- `DEBUG=1` — enables additional backend logging
- `SENDGRID_API_KEY` — enables the email delivery integration
- `FROM_EMAIL` — sender email for outgoing messages
- `FRONTEND_URL` — your deployed frontend URL, for example `https://yourdomain.com/`

Example `.env` (DO NOT commit real values):
```env
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_KEY=YOUR_SUPABASE_KEY
JWT_SECRET_KEY=YOUR_LONG_RANDOM_SECRET
DEBUG=1
FRONTEND_URL=https://your-app.vercel.app/
```

This project books rooms directly through the normal booking API and does not use Stripe Checkout.

### Service photos

Before saving service photos, run `database/migrations/20261025_service_images.sql` in your Supabase SQL Editor. This adds the optional `services.image_url` column without changing existing services.

Staff can add, replace, or remove a service photo in **Dashboard → Services → Add service / Edit**. Supported uploads are JPG, PNG, and WebP up to 2 MB. Photos are saved as data URLs in the database, using the same approach as the existing room photos. The service card uses the saved photo when available.

### 3) Run the API locally
```bash
python api/index.py
```

Then visit `http://localhost:5000/`. Flask serves the website from `public/` and the API from `/api`.

## Security notes
- Do **not** commit `.env` files or any keys.
- Do **not** put Supabase keys or JWT secrets directly into `public/assets/js/app.js` or `public/index.html`.
- If Supabase RLS is enabled, ensure you have the correct policies for:
  - Reading/writing `reviews`
  - Reading/writing `service_avails`
  - Any other tables you access from the API

## Project files

```text
Minnies Resort/
  public/                 Website files served to browsers
    index.html            Main Vue interface
    privacy.html          Privacy policy
    assets/
      css/style.css       Styles and responsive layout
      js/app.js           Frontend behavior and API calls
      images/             Logos and payment provider images
  api/
    index.py              Flask and Vercel entrypoint
    services/             Active payment, notification, and email modules
    legacy/               Earlier implementation, retained for reference
    requirements.txt      Backend dependencies
  docs/                   Setup and integration guides
  tests/                  Local structure and routing checks
  .env                    Local secrets (ignored by Git)
  requirements.txt        Deployment dependencies
  vercel.json             Hosting configuration
```

Keep the Vercel project root at this repository root. `vercel.json` sets `public/` as the static output directory and preserves `/api/*` routing. Public addresses remain `/`, `/privacy.html`, and `/assets/...`.

- `public/index.html` — main UI
- `public/assets/js/app.js` — Vue app logic + API calls
- `public/assets/css/style.css` — styling + responsive behavior
- `api/index.py` — Flask API for Vercel
- `vercel.json` — Vercel rewrites for `/api/*`

## Transaction notifications

For password-reset and transaction emails, run the additional [email migration](database/migrations/20261025_email_delivery.sql) and follow [email setup](docs/email-setup.md).

Run [the notification migration](database/migrations/20261025_notifications.sql) after all payment/counter migrations, then restart Flask and refresh the browser. Staff and guests get a private notification inbox for new requests and transaction updates. See [notification setup and behavior](docs/notifications.md).

## Troubleshooting

### UI changes not showing
Browsers can cache aggressively. Try:
- Hard refresh
- Clearing site data

### API calls returning HTML
If an API request returns HTML, it usually means the route is missing or a rewrite is incorrect.

### Supabase insert fails
Check:
- Table schema matches what the API sends
- RLS policies permit the operation

