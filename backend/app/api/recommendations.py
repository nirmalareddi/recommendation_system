"""
Recommendation generation endpoints.

This module:
1. Loads a student profile.
2. Loads all university/program reference data.
3. Restricts recommendations to New Zealand programs.
4. Scores and ranks eligible programs.
5. Generates personalized explanations.
6. Saves the recommendation.
7. Sends the recommendation email.
8. Returns the recommendations through the API.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config.settings import TOP_N_RECOMMENDATIONS
from app.database import get_db
from app.llm.explanation_service import generate_explanations
from app.models import db_models
from app.models.schemas import RecommendationItem, RecommendationOut
from app.notifications.email_service import send_recommendation_email
from app.scoring.scoring import (
    StudentProfile,
    UniversityProgram,
    rank_top_n,
)


router = APIRouter(
    prefix="/students",
    tags=["recommendations"],
)


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def _to_student_profile(student: db_models.Student) -> StudentProfile:
    """
    Convert the SQLAlchemy Student model into the scoring-layer
    StudentProfile object.
    """

    return StudentProfile(
        qualification=student.academic_qualification,
        field_of_study=student.field_of_study,
        preferred_course=student.preferred_course,
        preferred_country=student.preferred_country,
        marks_percentage=student.marks_percentage,
        cgpa=student.cgpa,
        budget_max_usd=student.budget_max_usd,
        english_test_score=student.english_test_score,
    )


def _to_university_program(
    university: db_models.University,
) -> UniversityProgram:
    """
    Convert the SQLAlchemy University model into the scoring-layer
    UniversityProgram object.
    """

    return UniversityProgram(
        id=university.id,
        name=university.name,
        country=university.country,
        program_name=university.program_name,
        required_qualification=university.required_qualification,
        field_of_study=university.field_of_study,
        degree_level=university.degree_level,
        min_marks_percentage_cutoff=university.min_marks_percentage_cutoff,
        seats_available=university.seats_available,
        annual_tuition_fee_usd=university.annual_tuition_fee_usd,
        min_english_test_score=university.min_english_test_score,
    )


# ---------------------------------------------------------------------------
# POST /students/{student_id}/recommendations
# ---------------------------------------------------------------------------


@router.post(
    "/{student_id}/recommendations",
    response_model=RecommendationOut,
    status_code=201,
)
def generate_and_send_recommendations(
    student_id: str,
    db: Session = Depends(get_db),
):
    """
    Generate the top university recommendations for a student,
    persist them, and send the recommendation email.
    """

    # -----------------------------------------------------------------------
    # 1. Find student
    # -----------------------------------------------------------------------

    student = (
        db.query(db_models.Student)
        .filter_by(id=student_id)
        .first()
    )

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student not found",
        )

    # -----------------------------------------------------------------------
    # 2. Load universities
    # -----------------------------------------------------------------------

    universities = (
        db.query(db_models.University)
        .all()
    )

    if not universities:
        raise HTTPException(
            status_code=400,
            detail="No university reference data seeded yet",
        )

    # -----------------------------------------------------------------------
    # 2A. New Zealand-only safeguard
    # -----------------------------------------------------------------------
    # The application currently recommends universities in New Zealand
    # only. Even if another country is accidentally added to the database,
    # it must never enter the recommendation/scoring pipeline.

    universities = [
        university
        for university in universities
        if university.country
        and university.country.strip().lower() == "new zealand"
    ]

    if not universities:
        raise HTTPException(
            status_code=422,
            detail="No New Zealand university programs are available",
        )

    # -----------------------------------------------------------------------
    # 3. Convert database objects into scoring objects
    # -----------------------------------------------------------------------

    student_profile = _to_student_profile(student)

    programs = [
        _to_university_program(university)
        for university in universities
    ]

    # Lookup dictionary so we can quickly get university details
    # after scoring.
    uni_lookup = {
        university.id: university
        for university in universities
    }

    # -----------------------------------------------------------------------
    # 4. Score and rank universities
    # -----------------------------------------------------------------------

    top_results = rank_top_n(
        student_profile,
        programs,
        n=TOP_N_RECOMMENDATIONS,
    )

    if not top_results:
        raise HTTPException(
            status_code=422,
            detail=(
                "No eligible universities found for this student's profile "
                "(check qualification, field of study, budget, "
                "English score, seats and academic cutoff)"
            ),
        )

    # Ordered university IDs.
    ranked_ids = [
        result.university_id
        for result in top_results
    ]

    # -----------------------------------------------------------------------
    # 5. Build recommendation items
    # -----------------------------------------------------------------------

    recommendation_items = []

    for result in top_results:
        university = uni_lookup[result.university_id]

        recommendation_items.append(
            {
                "university_id": result.university_id,
                "university_name": university.name,
                "country": university.country,
                "program_name": university.program_name,
                "field_of_study": university.field_of_study,
                "degree_level": university.degree_level,
                "score": result.score,
                "breakdown": result.breakdown,
            }
        )

    # -----------------------------------------------------------------------
    # 6. Prepare student information for explanation generation
    # -----------------------------------------------------------------------

    student_dict = {
        "name": student.name,
        "academic_qualification": student.academic_qualification,
        "field_of_study": student.field_of_study,
        "marks_percentage": student.marks_percentage,
        "cgpa": student.cgpa,
        "preferred_course": student.preferred_course,
        "preferred_country": student.preferred_country,
        "budget_max_usd": student.budget_max_usd,
        "english_test_score": student.english_test_score,
    }

    # -----------------------------------------------------------------------
    # 7. Generate personalized explanations
    # -----------------------------------------------------------------------

    explanation_results = generate_explanations(
        student_dict,
        recommendation_items,
    )

    explanation_by_uni_id = {
        explanation.university_id: explanation.explanation
        for explanation in explanation_results
    }

    # Attach explanation to every recommendation.
    for item in recommendation_items:
        item["explanation"] = explanation_by_uni_id.get(
            item["university_id"]
        )

    # -----------------------------------------------------------------------
    # 8. Prepare data for database persistence
    # -----------------------------------------------------------------------

    breakdown_by_uni = {
        item["university_id"]: {
            "score": item["score"],
            "explanation": item["explanation"],
            **item["breakdown"],
        }
        for item in recommendation_items
    }

    # -----------------------------------------------------------------------
    # 9. Save recommendation
    # -----------------------------------------------------------------------

    recommendation = db_models.Recommendation(
        student_id=student.id,
        ranked_university_ids=ranked_ids,
        score_breakdown=breakdown_by_uni,
        status="generated",
    )

    db.add(recommendation)
    db.commit()
    db.refresh(recommendation)

    # -----------------------------------------------------------------------
    # 10. Send recommendation email
    # -----------------------------------------------------------------------

    email_result = send_recommendation_email(
        to_email=student.contact_email,
        student_name=student.name,
        recommendation_items=recommendation_items,
    )

    # -----------------------------------------------------------------------
    # 11. Save notification log
    # -----------------------------------------------------------------------

    notification_log = db_models.NotificationLog(
        student_id=student.id,
        channel="email",
        status=email_result.status,
    )

    db.add(notification_log)

    # Mark recommendation as sent.
    recommendation.status = "sent"
    recommendation.sent_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(recommendation)

    # -----------------------------------------------------------------------
    # 12. Return API response
    # -----------------------------------------------------------------------

    return RecommendationOut(
        id=recommendation.id,
        student_id=recommendation.student_id,
        status=recommendation.status,
        generated_at=recommendation.generated_at,
        sent_at=recommendation.sent_at,
        recommendations=[
            RecommendationItem(
                university_id=item["university_id"],
                university_name=item["university_name"],
                country=item["country"],
                program_name=item["program_name"],
                field_of_study=item["field_of_study"],
                degree_level=item["degree_level"],
                score=item["score"],
                breakdown=item["breakdown"],
                explanation=item["explanation"],
            )
            for item in recommendation_items
        ],
    )


# ---------------------------------------------------------------------------
# GET /students/{student_id}/recommendations
# ---------------------------------------------------------------------------


@router.get(
    "/{student_id}/recommendations",
    response_model=list[RecommendationOut],
)
def get_recommendations_for_student(
    student_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve all previously generated recommendations for a student.
    """

    # -----------------------------------------------------------------------
    # 1. Check student exists
    # -----------------------------------------------------------------------

    student = (
        db.query(db_models.Student)
        .filter_by(id=student_id)
        .first()
    )

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student not found",
        )

    # -----------------------------------------------------------------------
    # 2. Load recommendations
    # -----------------------------------------------------------------------

    recommendations = (
        db.query(db_models.Recommendation)
        .filter_by(student_id=student_id)
        .all()
    )

    # -----------------------------------------------------------------------
    # 3. Load current university reference data
    # -----------------------------------------------------------------------

    universities = {
        university.id: university
        for university in (
            db.query(db_models.University)
            .all()
        )
    }

    output = []

    # -----------------------------------------------------------------------
    # 4. Reconstruct API response
    # -----------------------------------------------------------------------

    for recommendation in recommendations:

        items = []

        for university_id in recommendation.ranked_university_ids:

            stored = recommendation.score_breakdown.get(
                university_id,
                {},
            )

            score = stored.get(
                "score",
                0.0,
            )

            explanation = stored.get(
                "explanation",
            )

            # Remove fields that are represented separately
            # in RecommendationItem.
            breakdown = {
                key: value
                for key, value in stored.items()
                if key not in (
                    "score",
                    "explanation",
                )
            }

            university = universities.get(
                university_id
            )

            # If the university still exists in the reference table,
            # return its details. Otherwise return safe fallback values.
            items.append(
                RecommendationItem(
                    university_id=university_id,
                    university_name=(
                        university.name
                        if university
                        else "Unknown"
                    ),
                    country=(
                        university.country
                        if university
                        else "Unknown"
                    ),
                    program_name=(
                        university.program_name
                        if university
                        else "Unknown"
                    ),
                    field_of_study=(
                        university.field_of_study
                        if university
                        else None
                    ),
                    degree_level=(
                        university.degree_level
                        if university
                        else None
                    ),
                    score=score,
                    breakdown=breakdown,
                    explanation=explanation,
                )
            )

        output.append(
            RecommendationOut(
                id=recommendation.id,
                student_id=recommendation.student_id,
                status=recommendation.status,
                generated_at=recommendation.generated_at,
                sent_at=recommendation.sent_at,
                recommendations=items,
            )
        )

    return output