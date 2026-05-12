"""
Database connection setup — Changed 2026-05-12
===============================================
Reads DATABASE_URL from env. Falls back to local SQLite for dev.

Local dev:    no env var → sqlite:///crm.db
Local + Supabase:  export DATABASE_URL="postgresql://...:6543/postgres"
Vercel:       DATABASE_URL set in Vercel dashboard (use pooler, port 6543)

NullPool is used for Postgres because Vercel serverless functions are
short-lived — SQLAlchemy's connection pool is useless and harmful when
pgbouncer is pooling on Supabase's side. NullPool opens+closes per request;
pgbouncer handles the actual pooling.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///crm.db")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # Postgres / Supabase: pgbouncer handles pooling, so disable SQLAlchemy's
    engine = create_engine(DATABASE_URL, poolclass=NullPool)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
