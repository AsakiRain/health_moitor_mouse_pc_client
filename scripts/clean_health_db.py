#!/usr/bin/env python3
"""Clean incomplete health records from the PC client SQLite database.

By default this script runs in dry-run mode and only reports what would be
deleted. Pass --apply to actually delete incomplete records.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path


REQUIRED_FIELDS = (
    "heartrate",
    "spo2",
    "fatigue",
    "sdnn",
    "rr_interval",
    "systolic",
    "diastolic",
)


def default_db_path() -> Path:
    return Path(__file__).resolve().parents[1] / "history.db"


def build_keep_clause() -> str:
    return " AND ".join(f"COALESCE({field}, 0) > 0" for field in REQUIRED_FIELDS)


def backup_database(db_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_suffix(f".{timestamp}.bak")
    shutil.copy2(db_path, backup_path)
    return backup_path


def summarize_rows(con: sqlite3.Connection) -> tuple[int, int, int, Counter[str]]:
    keep_clause = build_keep_clause()
    total = con.execute("SELECT COUNT(*) FROM health_data").fetchone()[0]
    kept = con.execute(f"SELECT COUNT(*) FROM health_data WHERE {keep_clause}").fetchone()[0]
    removed = total - kept

    missing_reasons: Counter[str] = Counter()
    query = "SELECT " + ", ".join(REQUIRED_FIELDS) + " FROM health_data"
    for row in con.execute(query):
        for field, value in zip(REQUIRED_FIELDS, row):
            if value is None or int(value) <= 0:
                missing_reasons[field] += 1

    return total, kept, removed, missing_reasons


def clean_database(db_path: Path, apply: bool, backup: bool) -> int:
    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")

    con = sqlite3.connect(db_path)
    try:
        total, kept, removed, missing_reasons = summarize_rows(con)
        mode = "APPLY" if apply else "DRY-RUN"
        print(f"mode: {mode}")
        print(f"database: {db_path}")
        print(f"required_fields: {', '.join(REQUIRED_FIELDS)}")
        print(f"total_records: {total}")
        print(f"kept_records: {kept}")
        print(f"records_to_delete: {removed}")

        if missing_reasons:
            print("missing_or_zero_counts:")
            for field, count in missing_reasons.most_common():
                print(f"  {field}: {count}")

        if not apply:
            print("dry-run only; pass --apply to delete incomplete records.")
            return 0

        backup_path = None
        if backup:
            backup_path = backup_database(db_path)
            print(f"backup: {backup_path}")

        keep_clause = build_keep_clause()
        with con:
            con.execute(f"DELETE FROM health_data WHERE NOT ({keep_clause})")
        con.execute("VACUUM")

        total_after, kept_after, removed_after, _ = summarize_rows(con)
        print(f"deleted_records: {removed}")
        print(f"remaining_records: {total_after}")
        print(f"remaining_valid_records: {kept_after}")
        if removed_after != 0:
            print(f"warning: {removed_after} incomplete records still remain.")
            return 2
        return 0
    finally:
        con.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Keep only complete health_data rows in history.db.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=default_db_path(),
        help="Path to history.db. Defaults to the PC client history.db.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete incomplete rows. Without this, only reports counts.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a timestamped .bak copy before applying changes.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return clean_database(args.db.resolve(), args.apply, not args.no_backup)


if __name__ == "__main__":
    raise SystemExit(main())
