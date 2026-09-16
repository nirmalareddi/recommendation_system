"""
Student intake endpoints (Stage A of the POC plan).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import db_models
from app.models.schemas import StudentCreate, StudentOut

router = APIRouter(prefix="/students", tags=["students"])


@router.post("", response_model=StudentOut, status_code=201)
def create_student(payload: StudentCreate, db: Session = Depends(get_db)):
    student = db_models.Student(
        name=payload.name,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        academic_qualification=payload.academic_qualification,
        field_of_study=payload.field_of_study,
        marks_percentage=payload.marks_percentage,
        cgpa=payload.cgpa,
        budget_max_usd=payload.budget_max_usd,
        english_test_score=payload.english_test_score,
        preferred_course=payload.preferred_course,
        preferred_country=payload.preferred_country,
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


@router.get("/{student_id}", response_model=StudentOut)
def get_student(student_id: str, db: Session = Depends(get_db)):
    student = db.query(db_models.Student).filter_by(id=student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student
