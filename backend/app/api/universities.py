"""
University/program reference-data endpoints (Stage B of the POC plan).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import db_models
from app.models.schemas import UniversityCreate, UniversityOut

router = APIRouter(prefix="/universities", tags=["universities"])


@router.post("", response_model=UniversityOut, status_code=201)
def create_university(payload: UniversityCreate, db: Session = Depends(get_db)):
    university = db_models.University(**payload.model_dump())
    db.add(university)
    db.commit()
    db.refresh(university)
    return university


@router.get("", response_model=list[UniversityOut])
def list_universities(db: Session = Depends(get_db)):
    return db.query(db_models.University).all()
