# CLAUDE.md - AI Smart Civic Services

## Project Overview
AI-powered municipal complaint management platform built with FastAPI, SQLite, Gemini AI (triage & auto-routing), and a responsive SPA frontend (HTML5/Tailwind/Vanilla JS).

## Development & Test Commands
- **Run Development Server**: `uvicorn app.main:app --reload --port 8000`
- **Run Full Test Suite**: `pytest -v`
- **Run Specific Test File**: `pytest tests/test_complaints.py -v`
- **Install Dependencies**: `pip install -r requirements.txt`

## Architecture & Code Structure
- `app/main.py`: Entrypoint app factory wiring singletons (`DatabaseManager`, `AIAnalyzer`, `ComplaintManager`, `AnalyticsService`, `NotificationManager`).
- `app/services/`: Core domain & business logic.
  - `db_manager.py`: SQLite database abstraction layer (CRUD, schema init, migrations, seeding).
  - `ai_service.py`: Gemini 2.5 Flash API analyzer for category classification, priority prediction, and summary generation.
  - `complaint_manager.py`: End-to-end complaint lifecycle orchestrator (AI triage, SLA calculation, auto-routing).
  - `analytics_service.py`: Metric aggregation (counts, trends, resolution time stats).
  - `notification_manager.py`: Citizen & Admin notification storage and retrieval.
- `app/routes/`: FastAPI API endpoints (`complaint_routes.py`, `admin_routes.py`, `analytics_routes.py`, `user_routes.py`).
- `database/`: `schema.sql` defines tables (`users`, `admin_applications`, `departments`, `complaints`, `ai_analysis`, `notifications`, `sms_logs`, `audit_logs`).
- `app/static/`: SPA Frontend served statically from `/`.
  - `index.html`: Main SPA container for Citizen & Admin views.
  - `js/app.js`: Citizen authentication, map visualization (Leaflet), complaint submission, and chatbot drawer logic.
  - `js/admin.js`: Admin Command Center analytics (Chart.js), triage table management, and Super Admin RBAC modal.

## Key Coding Conventions & Engineering Principles
1. **Strict Tech Stack**: All backend development, server logic, database managers, and related services/tools MUST be written strictly in Python (FastAPI, Uvicorn, SQLite, Pytest, Pydantic, Google GenAI SDK).
2. **Clean Architecture**: Follow strict Clean OOP Architecture and Layered Separation of Concerns. Route handlers must NOT instantiate service classes directly; rely on dependency injection or `init_app`.
3. **Database Integrity**: All SQL statements belong inside `DatabaseManager` using parameterized queries with foreign key constraints enabled. No missing schema fields or database flaws allowed.
4. **AI Integration**: Gemini calls are strictly isolated within `AIAnalyzer`. Return fallback results gracefully on API failure.
5. **Zero Loopholes & Production Readiness**: Proactively detect and fix any logical flaws, edge-case loopholes, or architectural gaps. Code must physically exist, be fully runnable, and have zero placeholders or TODOs.
6. **Testing & Quality Control**: Maintain 100% pass status on the pytest suite (`pytest -v`).

