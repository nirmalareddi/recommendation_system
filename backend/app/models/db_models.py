"""
SQLAlchemy ORM models — students, universities, recommendations, notifications_log.

v3 changes:
- Student: marks_or_cgpa split into marks_percentage + cgpa (either may be
  provided); added budget_max_usd and field_of_study.
- University: added field_of_study and degree_level so programs can be
  matched against a student's academic background.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Student(Base):
    __tablename__ = "students"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    contact_email = Column(String, nullable=False)
    contact_phone = Column(String, nullable=True)
    academic_qualification = Column(String, nullable=False)
    field_of_study = Column(String, nullable=True)
    marks_percentage = Column(Float, nullable=True)   # 0-100 scale
    cgpa = Column(Float, nullable=True)                # 0-10 scale
    budget_max_usd = Column(Float, nullable=True)      # max annual tuition budget
    english_test_score = Column(Float, nullable=True)  # e.g. IELTS band
    preferred_course = Column(String, nullable=False)
    preferred_country = Column(String, nullable=False)
    submitted_at = Column(DateTime, default=_utcnow)

    recommendations = relationship("Recommendation", back_populates="student")


class University(Base):
    __tablename__ = "universities"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    country = Column(String, nullable=False)
    program_name = Column(String, nullable=False)

    # Qualification requirement and academic background
    required_qualification = Column(String, nullable=False)
    field_of_study = Column(String, nullable=True)
    degree_level = Column(String, nullable=True)

    min_marks_percentage_cutoff = Column(Float, nullable=False)
    seats_available = Column(Float, nullable=True)
    annual_tuition_fee_usd = Column(Float, nullable=True)
    min_english_test_score = Column(Float, nullable=True)
    application_deadline = Column(
        String,
        nullable=True
    )  # stored as ISO date string, informational for POC


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(String, primary_key=True, default=_uuid)
    student_id = Column(String, ForeignKey("students.id"), nullable=False)
    ranked_university_ids = Column(
        JSON,
        nullable=False
    )  # ordered list of university ids
    score_breakdown = Column(
        JSON,
        nullable=False
    )  # per-university breakdown + explanation, keyed by university id
    status = Column(String, default="generated")  # generated / sent
    generated_at = Column(DateTime, default=_utcnow)
    sent_at = Column(DateTime, nullable=True)

    student = relationship("Student", back_populates="recommendations")


class NotificationLog(Base):
    __tablename__ = "notifications_log"

    id = Column(String, primary_key=True, default=_uuid)
    student_id = Column(String, ForeignKey("students.id"), nullable=False)
    channel = Column(String, nullable=False)  # e.g. "email"
    status = Column(String, nullable=False)  # "sent" / "failed" / "console_logged"
    sent_at = Column(DateTime, default=_utcnow)