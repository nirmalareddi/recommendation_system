"""
Seeds the universities table from data/seed_universities.csv.

Run with:
    python -m app.seed
"""

import csv
import os

from app.database import SessionLocal, init_db
from app.models import db_models

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "seed_universities.csv")


def _float_or_none(value: str):
    return float(value) if value not in (None, "") else None


def seed_universities():
    init_db()
    db = SessionLocal()
    try:
        existing_count = db.query(db_models.University).count()
        if existing_count > 0:
            print(f"Universities table already has {existing_count} rows — skipping seed. "
                  f"Delete admissions_poc.db to reseed from scratch.")
            return

        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                uni = db_models.University(
                    name=row["name"],
                    country=row["country"],
                    program_name=row["program_name"],
                    required_qualification=row["required_qualification"],
                    min_marks_percentage_cutoff=float(row["min_marks_percentage_cutoff"]),
                    seats_available=_float_or_none(row.get("seats_available")),
                    annual_tuition_fee_usd=_float_or_none(row.get("annual_tuition_fee_usd")),
                    min_english_test_score=_float_or_none(row.get("min_english_test_score")),
                    application_deadline=row.get("application_deadline") or None,
                )
                db.add(uni)
                count += 1
            db.commit()
            print(f"Seeded {count} university/program records.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_universities()
