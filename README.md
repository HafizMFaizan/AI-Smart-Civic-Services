# AI Smart Civic Services

An AI-assisted civic complaint triage system. Citizens submit complaints; Gemini
classifies the category and priority and writes a short actionable summary;
admins review, assign, and resolve complaints from a simple dashboard.

## Architecture

```
Citizen/Admin UI (single-page app) -> FastAPI Routes -> Services -> DatabaseManager -> SQLite
```

Services: `ComplaintManager`, `AIAnalyzer`, `AnalyticsService`, `NotificationManager`.
Gemini calls are isolated entirely inside `AIAnalyzer`; routes never touch SQL or
Gemini directly.

## Installation

1. Create and activate a virtual environment (recommended).
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Environment Setup

Copy `.env.example` to `.env` and set your Gemini API key:
```
GEMINI_API_KEY=your-key-here
```
If `GEMINI_API_KEY` is not set (or the Gemini API call fails), the app still
works: `AIAnalyzer` automatically falls back to a safe default result
(category `Other`, priority `Medium`, a generic summary) instead of failing
the request, and the complaint is always saved either way.

## Database Initialization

The SQLite database is created automatically on application startup from
`database/schema.sql` (`CREATE TABLE IF NOT EXISTS`, safe to run repeatedly)
at `database/civic_services.db`. No manual step is required.

## Running the Application

```bash
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000/ — a single-page app (Tailwind CSS via CDN,
vanilla JS). Use the "Citizen" / "Admin" links in the header to switch views
(`#/` and `#/admin`) without a page reload. `/admin.html` still exists and
redirects into the SPA's admin view, for anyone with an old bookmark.

## API Areas

All endpoints are prefixed with `/api`.

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Health check |
| POST | `/api/users` | Register a new citizen (role is always forced to `citizen`) |
| POST | `/api/complaints` | Submit a complaint (goes through `ComplaintManager`) |
| GET | `/api/citizens/{user_id}/complaints` | A citizen's complaints with status/AI info |
| GET | `/api/citizens/{user_id}/notifications` | A citizen's notifications |
| PATCH | `/api/notifications/{notification_id}/read` | Mark a notification as read |
| GET | `/api/admin/complaints` | All complaints for the admin dashboard, optionally filtered by `category`, `priority`, `status`, `department_id`, `location`, `search`, `date_from`, `date_to` (admin only) |
| PATCH | `/api/admin/complaints/{complaint_id}/status` | Update a complaint's status; notifies the citizen (admin only) |
| GET | `/api/analytics/dashboard` | Total / by-category / by-priority / by-status / by-department counts, including the `"Unassigned"` and `"Unanalyzed"` buckets (admin only) |
| GET | `/api/analytics/trends?group_by=day\|week\|month` | Complaint counts bucketed over time (admin only) |
| GET | `/api/analytics/resolution-time` | Average/minimum/maximum resolution time in hours and resolved count, based on `complaints.resolved_at` (admin only) |

Complaint response objects (`CitizenComplaintResponse` / `AdminComplaintResponse`)
use `date`, `assigned_department`, and `ai_summary` as field names, aligned with
the project specification's Complaint object vocabulary. `complaint_id` and
`department_id` remain integers (not UUIDs) — the underlying database stays
normalized and integer-keyed; only the API-facing field names changed.

## Frontend URLs

- `/` — single-page app: citizen registration/complaint form/complaint list/notifications, and the admin dashboard, toggled via `#/` and `#/admin`
- `/admin.html` — redirect stub into `/#/admin`, kept for old bookmarks

## Authentication Limitation

**There is still no password, session, token, or OAuth infrastructure.** This
was an explicit, documented scope limit from Phase 3 onward, not an
oversight. `POST /api/users` (added in Phase 4B) lets a citizen obtain a real
`user_id` through the app instead of needing one seeded manually — but it
does not add authentication:

- Citizen endpoints trust whatever `user_id` the client supplies — there is no
  verification that the caller actually owns that id.
- Admin endpoints require an `X-User-Id` header naming a user whose `role`
  column in the `users` table is `admin`. This is the minimum role check the
  existing schema supports, checked via `DatabaseManager.get_user_role()` —
  **not** real authentication. Anyone who knows or guesses an admin's user id
  can act as that admin.
- **A default admin is seeded automatically** on first database
  initialization (`DatabaseManager.initialize_database()`), so a fresh
  deployment always has at least one usable admin instead of the admin API
  being permanently unreachable. On a genuinely empty database this is user
  id `1` (name "Default Admin", email `admin@civicservices.local`); seeding
  is skipped if any admin already exists. Because this default is
  predictable, `X-User-Id: 1` should be treated as a known, public "no
  auth" convenience for a demo/hackathon deployment, not a secret — the
  same limitation as every other part of this authentication model.
- `POST /api/users` is intentionally public (a brand-new citizen has no
  `user_id` yet to prove anything with) and always creates `role='citizen'`
  server-side — it never accepts a client-supplied role, so it cannot be used
  to self-promote to admin.
- `PATCH /api/notifications/{notification_id}/read` has no ownership check —
  consistent with (not worse than) the existing notification-listing
  endpoint, since anyone can already read any user's notifications.

A real deployment would need actual credential storage, session/token
issuance, and route-level enforcement tied to a verified identity — none of
which exist yet.

## Running Tests

```bash
pytest tests/ -v
```

## Deployment

This app is a single long-running FastAPI/Uvicorn process that reads and
writes a local SQLite file (`database/civic_services.db`) and serves static
frontend files directly from disk. That combination requires a host with a
**persistent process and a persistent, writable filesystem** — it is not a
stateless request/response function.

**Vercel is not suitable without changing the architecture.** Vercel's
Python support runs as serverless functions with an ephemeral filesystem —
writes to SQLite would not reliably persist between invocations, and there
is no supported way to keep a long-lived Uvicorn process running. Making
Vercel work would require replacing SQLite with a hosted database, which is
out of scope here (this project intentionally keeps its existing SQLite +
DatabaseManager design).

**Recommended**: any platform that runs a persistent Python web service with
a persistent disk — for example Render, Railway, or Fly.io (or a plain VPS).
All of these can run this app with no code changes and no Dockerfile:

1. Install dependencies: `pip install -r requirements.txt`
2. Set the `GEMINI_API_KEY` environment variable in the platform's own
   environment/secrets configuration (not a committed `.env` file).
3. Ensure `database/` is on a persistent volume/disk if the platform
   distinguishes ephemeral vs. persistent storage.
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   (use the platform's injected `$PORT`; for local dev, `--reload` on the
   default port 8000 is used instead, as shown above).

The SPA uses hash-based routing (`#/`, `#/admin`), not `pushState`-based
routing, so no server-side catch-all/rewrite rule is needed for the
frontend — `/`, `/admin.html`, `/css/*`, `/js/*`, and `/api/*` are all
literal paths already served correctly by the existing static file mount
and API routers.
