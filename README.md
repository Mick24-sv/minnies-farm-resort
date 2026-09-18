# Minnie's Farm Resort — Website (Vue + Flask on Vercel + Supabase)

Hi, I'm Mick — a full-stack developer focused on building practical web apps for real businesses. I design and develop modern booking systems, customer-facing interfaces, and backend services that make operations smoother and more efficient.

This repository contains the **Minnie's Farm Resort** room booking website.

- **Frontend:** Static HTML/CSS + Vue (loaded via `index.html`, logic in `app.js`)
- **Backend API:** Flask app deployed as a Vercel Serverless Function (`api/index.py`)
- **Database:** Supabase (PostgREST)

## How the app works

### Frontend (client)
The UI is a single-page experience controlled by Vue state.

- `index.html` defines the page structure (Home, Rooms, Room Detail, Services, Dashboards, modals).
- `app.js` holds the Vue app state and calls the backend API using `fetch()`.
- `style.css` provides the styling and responsive layout.

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
This repo is designed to deploy to Vercel.

- Requests to `/api/*` are routed to the Flask serverless function (`api/index.py`).
- All other routes serve the static frontend.

## Local development

### 1) Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2) Set environment variables
Create a `.env` file in the project root (this repo ignores `.env` via `.gitignore`).

Required variables:
- `SUPABASE_URL` — your Supabase project URL
- `SUPABASE_KEY` — your Supabase API key
- `JWT_SECRET_KEY` — a strong secret string used to sign JWTs

Optional:
- `DEBUG=1` — enables additional backend logging
- `SENDGRID_API_KEY` — required only if you wire up real email delivery
- `FROM_EMAIL` — sender email for outgoing messages
- `STRIPE_SECRET_KEY` — your Stripe secret key for Checkout sessions
- `STRIPE_WEBHOOK_SECRET` — webhook signing secret from Stripe
- `FRONTEND_URL` — your deployed frontend URL, for example `https://yourdomain.com/`

Example `.env` (DO NOT commit real values):
```env
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_KEY=YOUR_SUPABASE_KEY
JWT_SECRET_KEY=YOUR_LONG_RANDOM_SECRET
DEBUG=1
STRIPE_SECRET_KEY=sk_test_xxxxxxxxxxxxxxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxx
FRONTEND_URL=https://your-app.vercel.app/
```

### Stripe setup
To enable real online payments for bookings:

1. Create a Stripe account and get your test or live secret keys.
2. Add the key values above to your environment.
3. In Stripe Dashboard, create a webhook endpoint for `/api/payments/webhook`.
4. Select events such as `checkout.session.completed`.
5. Copy the webhook signing secret into `STRIPE_WEBHOOK_SECRET`.
6. Test checkout using Stripe test cards.

This project is already wired to create a Stripe Checkout session when a guest books a room, and it falls back to the normal booking flow if Stripe is not configured yet.

### 3) Run the API locally
```bash
python api/index.py
```

Then open `index.html` via a local static server (recommended) or your IDE live server.

## Security notes
- Do **not** commit `.env` files or any keys.
- Do **not** put Supabase keys or JWT secrets directly into `app.js` or `index.html`.
- If Supabase RLS is enabled, ensure you have the correct policies for:
  - Reading/writing `reviews`
  - Reading/writing `service_avails`
  - Any other tables you access from the API

## Project files
- `index.html` — main UI
- `app.js` — Vue app logic + API calls
- `style.css` — styling + responsive behavior
- `api/index.py` — Flask API for Vercel
- `vercel.json` — Vercel rewrites for `/api/*`

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

