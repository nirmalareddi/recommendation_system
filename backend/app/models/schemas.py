"""
Pydantic schemas — request/response validation for the API layer.

Kept separate from the SQLAlchemy models (db_models.py) so DB structure
can evolve without automatically changing the public API contract.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class StudentCreate(BaseModel):
    name: str = Field(..., min_length=1)
    contact_email: EmailStr
    contact_phone: str = Field(..., min_length=1)

    academic_qualification: str = Field(..., min_length=1)
    field_of_study: str = Field(..., min_length=1)

    # Student must provide at least one of these.
    # Providing both is also allowed.
    marks_percentage: Optional[float] = None
    cgpa: Optional[float] = None

    budget_max_usd: float = Field(..., ge=0)

    # POC currently treats this as an IELTS-style band.
    english_test_score: float = Field(..., ge=0, le=9)

    preferred_course: str = Field(..., min_length=1)
    preferred_country: str = Field(..., min_length=1)

    @field_validator("marks_percentage")
    @classmethod
    def marks_in_valid_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0 or v > 100):
            raise ValueError("marks_percentage must be between 0 and 100")
        return v

    @field_validator("cgpa")
    @classmethod
    def cgpa_in_valid_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0 or v > 10):
            raise ValueError("cgpa must be between 0 and 10")
        return v

    @model_validator(mode="after")
    def require_marks_or_cgpa(self):
        if self.marks_percentage is None and self.cgpa is None:
            raise ValueError(
                "Provide at least one of marks_percentage or cgpa"
            )
        return self


class StudentOut(BaseModel):
    id: str
    name: str
    contact_email: str
    contact_phone: str
    academic_qualification: str
    field_of_study: str
    marks_percentage: Optional[float] = None
    cgpa: Optional[float] = None
    budget_max_usd: float
    english_test_score: float
    preferred_course: str
    preferred_country: str
    submitted_at: datetime

    class Config:
        from_attributes = True


class UniversityCreate(BaseModel):
    name: str
    country: str
    program_name: str
    required_qualification: str
    field_of_study: Optional[str] = None
    degree_level: Optional[str] = None
    min_marks_percentage_cutoff: float
    seats_available: Optional[float] = None
    annual_tuition_fee_usd: Optional[float] = None
    min_english_test_score: Optional[float] = None
    application_deadline: Optional[str] = None


class UniversityOut(UniversityCreate):
    id: str

    class Config:
        from_attributes = True


class RecommendationItem(BaseModel):
    university_id: str
    university_name: str

    # University/program details used by the frontend recommendation cards.
    country: str
    program_name: str
    field_of_study: Optional[str] = None
    degree_level: Optional[str] = None

    score: float
    breakdown: dict
    explanation: Optional[str] = None


class RecommendationOut(BaseModel):
    id: str
    student_id: str
    status: str
    generated_at: datetime
    sent_at: Optional[datetime] = None
    recommendations: list[RecommendationItem]

    class Config:
        from_attributes = True