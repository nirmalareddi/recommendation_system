"""
Recommendation generation endpoint — ties together Stages C, D, and E of
the POC plan: score + rank a student against all universities, generate a
personalized explanation for each pick (LLM, or template fallback),
persist the result, and fire the notification immediately (no approval
gate in this version of the plan).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database import get_db
from app.models import db_models
from app.models.schemas import RecommendationOut, RecommendationItem
from app.scoring.scoring import StudentProfile, UniversityProgram, rank_top_n
from app.llm.explanation_service import generate_explanations
from app.notifications.email_service import send_recommendation_email
from app.config.settings import TOP_N_RECOMMENDATIONS

router = APIRouter(prefix="/students", tags=["recommendations"])


def _to_student_profile(student: db_models.Student) -> StudentProfile:
    return StudentProfile(
        qualification=student.academic_qualification,
        preferred_course=student.preferred_course,
        preferred_country=student.preferred_country,
        marks_percentage=student.marks_percentage,
        cgpa=student.cgpa,
        budget_max_usd=student.budget_max_usd,
        english_test_score=student.english_test_score,
    )


def _to_university_program(uni: db_models.University) -> UniversityProgram:
    return UniversityProgram(
        id=uni.id,
        name=uni.name,
        country=uni.country,
        program_name=uni.program_name,
        required_qualification=uni.required_qualification,
        min_marks_percentage_cutoff=uni.min_marks_percentage_cutoff,
        seats_available=uni.seats_available,
        annual_tuition_fee_usd=uni.annual_tuition_fee_usd,
        min_english_test_score=uni.min_english_test_score,
    )


@router.post("/{student_id}/recommendations", response_model=RecommendationOut, status_code=201)
def generate_and_send_recommendations(student_id: str, db: Session = Depends(get_db)):
    student = db.query(db_models.Student).filter_by(id=student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    universities = db.query(db_models.University).all()
    if not universities:
        raise HTTPException(status_code=400, detail="No university reference data seeded yet")

    student_profile = _to_student_profile(student)
    programs = [_to_university_program(u) for u in universities]
    uni_lookup = {u.id: u for u in universities}

    top_results = rank_top_n(student_profile, programs, n=TOP_N_RECOMMENDATIONS)

    if not top_results:
        raise HTTPException(
            status_code=422,
            detail="No eligible universities found for this student's profile "
                   "(check qualification, budget, seat availability and cutoffs)",
        )

    ranked_ids = [r.university_id for r in top_results]

    # Build the plain items list once — reused for explanation generation,
    # email body, persistence, and the API response.
    recommendation_items = [
        {
            "university_id": r.university_id,
            "university_name": uni_lookup[r.university_id].name,
            "score": r.score,
            "breakdown": r.breakdown,
        }
        for r in top_results
    ]

    student_dict = {
        "name": student.name,
        "academic_qualification": student.academic_qualification,
        "field_of_study": student.field_of_study,
        "marks_percentage": student.marks_percentage,
        "cgpa": student.cgpa,
        "preferred_course": student.preferred_course,
        "preferred_country": student.preferred_country,
        "budget_max_usd": student.budget_max_usd,
    }

    # Stage C.5 (new): generate a personalized explanation per recommendation —
    # LLM-written if ANTHROPIC_API_KEY is set, template fallback otherwise.
    explanation_results = generate_explanations(student_dict, recommendation_items)
    explanation_by_uni_id = {e.university_id: e.explanation for e in explanation_results}
    for item in recommendation_items:
        item["explanation"] = explanation_by_uni_id.get(item["university_id"])

    breakdown_by_uni = {
        item["university_id"]: {
            "score": item["score"],
            "explanation": item["explanation"],
            **item["breakdown"],
        }
        for item in recommendation_items
    }

    recommendation = db_models.Recommendation(
        student_id=student.id,
        ranked_university_ids=ranked_ids,
        score_breakdown=breakdown_by_uni,
        status="generated",
    )
    db.add(recommendation)
    db.commit()
    db.refresh(recommendation)

    # Stage E: fire notification immediately — no approval step in this plan version.
    email_result = send_recommendation_email(
        to_email=student.contact_email,
        student_name=student.name,
        recommendation_items=recommendation_items,
    )

    notification_log = db_models.NotificationLog(
        student_id=student.id,
        channel="email",
        status=email_result.status,
    )
    db.add(notification_log)

    recommendation.status = "sent"
    recommendation.sent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(recommendation)

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
                score=item["score"],
                breakdown=item["breakdown"],
                explanation=item["explanation"],
            )
            for item in recommendation_items
        ],
    )


@router.get("/{student_id}/recommendations", response_model=list[RecommendationOut])
def get_recommendations_for_student(student_id: str, db: Session = Depends(get_db)):
    student = db.query(db_models.Student).filter_by(id=student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    recs = db.query(db_models.Recommendation).filter_by(student_id=student_id).all()
    universities = {u.id: u for u in db.query(db_models.University).all()}

    output = []
    for rec in recs:
        items = []
        for uni_id in rec.ranked_university_ids:
            stored = rec.score_breakdown.get(uni_id, {})
            score = stored.get("score", 0.0)
            explanation = stored.get("explanation")
            breakdown = {k: v for k, v in stored.items() if k not in ("score", "explanation")}
            uni = universities.get(uni_id)
            items.append(
                RecommendationItem(
                    university_id=uni_id,
                    university_name=uni.name if uni else "Unknown",
                    score=score,
                    breakdown=breakdown,
                    explanation=explanation,
                )
            )
        output.append(
            RecommendationOut(
                id=rec.id,
                student_id=rec.student_id,
                status=rec.status,
                generated_at=rec.generated_at,
                sent_at=rec.sent_at,
                recommendations=items,
            )
        )
    return output
