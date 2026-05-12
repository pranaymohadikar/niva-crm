"""
Niva Bupa CRM — Database Upgrade Script — Changed 2026-05-12
=============================================================
Adds new tables and columns to an existing database WITHOUT dropping data.
Works on both SQLite (local) and Postgres (Supabase).

Usage:
  python scripts/upgrade.py                          # local SQLite
  DATABASE_URL=postgresql://... python scripts/upgrade.py    # Supabase

What it does:
  1. Checks which tables exist
  2. Creates any missing tables (CREATE TABLE)
  3. Checks which columns exist in each table
  4. Adds any missing columns (ALTER TABLE ADD COLUMN)
  5. Never drops, deletes, or modifies existing data

Safe to run multiple times — it skips anything that already exists.

Limitations:
  - Does NOT detect column type changes or renames
  - Does NOT remove columns or tables
  - Does NOT alter indexes (add them manually in Supabase if needed)
"""

import os
import sys
from pathlib import Path

# Allow importing db.py and models.py from ../api — Changed 2026-05-12
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

from db import engine, DATABASE_URL
from models import Base
from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateColumn


def upgrade():
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    model_tables = Base.metadata.tables
    is_sqlite = DATABASE_URL.startswith("sqlite")

    print("=" * 50)
    print("  Niva Bupa CRM — Database Upgrade")
    print("=" * 50)
    # Mask password in URL for logging
    import re
    safe_url = re.sub(r'://([^:]+):[^@]+@', r'://\1:***@', DATABASE_URL)
    print(f"  Database: {safe_url}")
    print(f"  Dialect:  {'SQLite' if is_sqlite else 'Postgres'}")
    print(f"  Existing tables: {len(existing_tables)}")
    print(f"  Model tables: {len(model_tables)}")
    print()

    changes = 0

    for table_name, table in model_tables.items():
        if table_name not in existing_tables:
            print(f"  + Creating table: {table_name}")
            table.create(engine)
            changes += 1
            continue

        # Table exists — check for missing columns
        existing_cols = {col['name'] for col in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name in existing_cols:
                continue

            # Render column DDL using the engine's dialect — Changed 2026-05-12
            # This produces correct SQL for both SQLite and Postgres.
            try:
                col_ddl = str(CreateColumn(column).compile(engine))
            except Exception as e:
                print(f"  ! Could not render DDL for {table_name}.{column.name}: {e}")
                continue

            # SQLite cannot ALTER TABLE ADD COLUMN with NOT NULL unless a default exists.
            # Relax to NULL for safety on existing rows (Postgres handles this fine too).
            if "NOT NULL" in col_ddl.upper() and "DEFAULT" not in col_ddl.upper():
                col_ddl = col_ddl.replace("NOT NULL", "").replace("not null", "")

            sql = f'ALTER TABLE {table_name} ADD COLUMN {col_ddl}'
            try:
                with engine.connect() as conn:
                    conn.execute(text(sql))
                    conn.commit()
                print(f"  + Added column: {table_name}.{column.name}")
                changes += 1
            except Exception as e:
                msg = str(e).lower()
                if "duplicate" in msg or "already exists" in msg:
                    pass  # Race condition or already present — skip silently
                else:
                    print(f"  ! Failed to add {table_name}.{column.name}: {e}")

    if changes == 0:
        print("  No changes needed — database is up to date.")
    else:
        print(f"\n  ✓ {changes} changes applied.")

    # Final summary
    inspector = inspect(engine)
    print(f"\n  Tables now: {len(inspector.get_table_names())}")
    for t in sorted(inspector.get_table_names()):
        cols = len(inspector.get_columns(t))
        print(f"    {t}: {cols} columns")

    print("\n  Data untouched ✓")
    print("=" * 50)


if __name__ == "__main__":
    upgrade()
