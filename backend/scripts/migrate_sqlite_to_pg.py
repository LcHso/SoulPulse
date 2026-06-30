"""
SQLite to PostgreSQL one-time data migration script.

Usage:
    python scripts/migrate_sqlite_to_pg.py [--source SQLITE_PATH] [--target PG_URL]

Defaults:
    source: ./soulpulse.db
    target: DATABASE_URL environment variable

This script:
1. Reads all tables from the source SQLite database
2. Truncates target PostgreSQL tables (idempotent - safe to re-run)
3. Batch-inserts all rows into PostgreSQL (1000 rows at a time)
4. Temporarily disables FK constraints during insert
5. Verifies row counts match between source and target
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, MetaData, text, inspect

# Load env from backend/.env
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

BATCH_SIZE = 1000


def get_default_target_url() -> str:
    """Get PostgreSQL URL from environment, converting async URL to sync if needed."""
    url = os.getenv("DATABASE_URL", "")
    # Convert async driver to sync driver for this migration script
    if "asyncpg" in url:
        url = url.replace("postgresql+asyncpg", "postgresql+psycopg2")
    elif url.startswith("postgresql://") or url.startswith("postgres://"):
        # Plain URL without driver specified - add psycopg2
        url = url.replace("postgresql://", "postgresql+psycopg2://")
        url = url.replace("postgres://", "postgresql+psycopg2://")
    return url


def migrate(source_path: str, target_url: str):
    """
    Migrate all data from SQLite to PostgreSQL.

    Args:
        source_path: Path to SQLite database file
        target_url: PostgreSQL connection URL (synchronous, psycopg2)
    """
    # Validate source
    if not Path(source_path).exists():
        print(f"[ERROR] Source SQLite file not found: {source_path}")
        sys.exit(1)

    if not target_url:
        print("[ERROR] No target PostgreSQL URL provided.")
        print("  Set DATABASE_URL env var or use --target argument.")
        sys.exit(1)

    if "sqlite" in target_url:
        print("[ERROR] Target URL appears to be SQLite. Target must be PostgreSQL.")
        sys.exit(1)

    source_url = f"sqlite:///{source_path}"

    print(f"[migrate] Source: {source_path}")
    print(f"[migrate] Target: {target_url.split('@')[0]}@***")  # Hide password
    print()

    # Create engines
    source_engine = create_engine(source_url)
    target_engine = create_engine(target_url)

    # Reflect source metadata
    source_meta = MetaData()
    source_meta.reflect(bind=source_engine)

    # Reflect target metadata
    target_meta = MetaData()
    target_meta.reflect(bind=target_engine)

    # Get table names from source
    source_tables = list(source_meta.tables.keys())
    print(f"[migrate] Found {len(source_tables)} tables in source")
    print()

    # Check which tables exist in target
    target_inspector = inspect(target_engine)
    target_table_names = target_inspector.get_table_names()

    results = {}  # table -> (source_count, target_count)

    with target_engine.begin() as target_conn:
        # Disable FK constraints for PostgreSQL during migration
        target_conn.execute(text("SET session_replication_role = 'replica'"))

        for table_name in source_tables:
            if table_name not in target_table_names:
                print(f"  [SKIP] {table_name} - not found in target (run create_all first)")
                continue

            source_table = source_meta.tables[table_name]
            target_table = target_meta.tables[table_name]

            # Read all rows from source
            with source_engine.connect() as source_conn:
                rows = source_conn.execute(source_table.select()).fetchall()

            source_count = len(rows)

            # Truncate target table (idempotent)
            target_conn.execute(text(f'TRUNCATE TABLE "{table_name}" CASCADE'))

            if source_count == 0:
                print(f"  [OK] {table_name}: 0 rows (empty)")
                results[table_name] = (0, 0)
                continue

            # Get column names from source table
            col_names = [col.name for col in source_table.columns]

            # Filter to only columns that exist in target
            target_col_names = [col.name for col in target_table.columns]
            common_cols = [c for c in col_names if c in target_col_names]

            # Batch insert
            inserted = 0
            for i in range(0, source_count, BATCH_SIZE):
                batch = rows[i:i + BATCH_SIZE]
                # Convert rows to dicts with only common columns
                batch_dicts = []
                for row in batch:
                    row_dict = {}
                    for col in common_cols:
                        val = getattr(row, col, None) if hasattr(row, col) else row._mapping.get(col)
                        row_dict[col] = val
                    batch_dicts.append(row_dict)

                if batch_dicts:
                    target_conn.execute(target_table.insert(), batch_dicts)
                    inserted += len(batch_dicts)

            print(f"  [OK] {table_name}: {inserted} rows migrated")
            results[table_name] = (source_count, inserted)

        # Re-enable FK constraints
        target_conn.execute(text("SET session_replication_role = 'origin'"))

        # Reset sequences for tables with auto-increment IDs
        print()
        print("[migrate] Resetting PostgreSQL sequences...")
        for table_name in source_tables:
            if table_name not in target_table_names:
                continue
            target_table = target_meta.tables[table_name]
            # Find columns with sequences (typically 'id')
            for col in target_table.columns:
                if col.autoincrement and col.primary_key:
                    seq_name = f"{table_name}_{col.name}_seq"
                    try:
                        target_conn.execute(text(
                            f"SELECT setval(pg_get_serial_sequence('{table_name}', '{col.name}'), "
                            f"COALESCE((SELECT MAX({col.name}) FROM \"{table_name}\"), 1), true)"
                        ))
                    except Exception:
                        # Sequence might not exist for this column
                        pass

    # Verification
    print()
    print("[migrate] Verification:")
    all_ok = True
    for table_name, (src_count, tgt_count) in results.items():
        status = "OK" if src_count == tgt_count else "MISMATCH"
        if status == "MISMATCH":
            all_ok = False
        print(f"  [{status}] {table_name}: source={src_count}, target={tgt_count}")

    print()
    if all_ok:
        print("[migrate] Migration completed successfully!")
    else:
        print("[migrate] WARNING: Some tables have row count mismatches!")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Migrate SoulPulse data from SQLite to PostgreSQL"
    )
    parser.add_argument(
        "--source",
        default="./soulpulse.db",
        help="Path to source SQLite database (default: ./soulpulse.db)",
    )
    parser.add_argument(
        "--target",
        default=None,
        help="Target PostgreSQL URL (default: from DATABASE_URL env var)",
    )
    args = parser.parse_args()

    target_url = args.target or get_default_target_url()

    try:
        migrate(args.source, target_url)
    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        print("[ERROR] All changes have been rolled back.")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
