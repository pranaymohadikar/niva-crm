# Niva Bupa CRM

FastAPI + SQLAlchemy CRM for tracking patient journeys across coaching modules.

## Local development

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run locally with SQLite (uses ./crm.db)
python -m uvicorn api.server:app --reload --port 8000

# OR run locally against Supabase
export DATABASE_URL="postgresql://postgres.PROJECT:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres"
python -m uvicorn api.server:app --reload --port 8000
```

Open <http://localhost:8000>. Default admin: `admin` / `admin123`.

## Migration (one-time, from CSV/Excel)

```bash
# Local SQLite
ALLOW_DROP=yes python scripts/migrate.py inside_sales.csv ops_tracker.xlsx

# Supabase — use DIRECT URL (port 5432), not pooler
export DATABASE_URL="postgresql://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres"
ALLOW_DROP=yes python scripts/migrate.py inside_sales.csv ops_tracker.xlsx
```

## Schema upgrades (after adding columns/tables to models.py)

```bash
# Local SQLite
python scripts/upgrade.py

# Supabase — direct URL recommended for DDL
DATABASE_URL="postgresql://...:5432/postgres" python scripts/upgrade.py
```

Safe to run repeatedly. Adds missing tables/columns; never drops or modifies data.

## Deploying to Vercel

1. Push this repo to GitHub
2. In Vercel: New Project → Import the repo
3. Framework preset: Other (Vercel auto-detects Python from `vercel.json`)
4. Add environment variable:
   - `DATABASE_URL` = Supabase **pooler** URL (port 6543, Transaction mode)
5. Deploy

Vercel will install `requirements.txt`, bundle `api/`, and serve the FastAPI app.

## File layout

```
api/                FastAPI app (deployed to Vercel)
  server.py         Routes, business logic
  models.py         SQLAlchemy models
  db.py             Engine setup (env-driven)
  crm.html          Frontend, served at /
scripts/            Run locally only
  migrate.py        One-time bulk import from CSV/Excel
  upgrade.py        Incremental schema changes
vercel.json         Vercel routing
requirements.txt    Runtime deps (slim, for Vercel)
requirements-dev.txt  Local + migration deps (adds pandas, uvicorn)
```
