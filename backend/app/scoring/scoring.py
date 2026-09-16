"""
Eligibility + merit scoring engine.

v2: now considers CGPA (converted to a percentage-equivalent), budget vs
tuition fee, seat availability, and an optional English test score cutoff
— on top of the existing qualification/marks/course/country logic.

Kept isolated and dependency-free (pure functions operating on plain
dataclasses) so it's easy to unit test and easy to swap/tune weights
without touching the API or DB layer.
"""

from dataclasses import dataclass
from typing import Optional

from app.scoring.config import SCORING_WEIGHTS, MARKS_RATIO_CAP
from app.config.settings import CGPA_TO_PERCENTAGE_MULTIPLIER


@dataclass
class StudentProfile:
    qualification: str
    preferred_course: str
    preferred_country: str
    marks_percentage: Optional[float] = None
    cgpa: Optional[float] = None
    budget_max_usd: Optional[float] = None
    english_test_score: Optional[float] = None


@dataclass
class UniversityProgram:
    id: str
    name: str
    country: str
    program_name: str
    required_qualification: str
    min_marks_percentage_cutoff: float
    seats_available: Optional[float] = None
    annual_tuition_fee_usd: Optional[float] = None
    min_english_test_score: Optional[float] = None


@dataclass
class ScoreResult:
    university_id: str
    eligible: bool
    score: float
    breakdown: dict


def normalized_academic_percentage(student: StudentProfile) -> float:
    """
    Returns the student's academic score as a percentage-equivalent, so it
    can be compared against a university's percentage-based cutoff
    regardless of whether the student reported marks_percentage or cgpa.

    If both are provided, marks_percentage takes precedence (it's a direct
    percentage, not an approximation). If only cgpa is provided, it's
    converted using CGPA_TO_PERCENTAGE_MULTIPLIER — a common approximation,
    not an exact institutional conversion; revisit this before relying on
    it for real decisions.
    """
    if student.marks_percentage is not None:
        return student.marks_percentage
    if student.cgpa is not None:
        return student.cgpa * CGPA_TO_PERCENTAGE_MULTIPLIER
    raise ValueError("Student profile has neither marks_percentage nor cgpa set")


def ineligibility_reason(student: StudentProfile, program: UniversityProgram) -> Optional[str]:
    """
    Hard eligibility filters, checked in order. Returns None if eligible,
    otherwise a short machine-readable reason string. Kept as pass/fail
    gates (no partial credit) — merit scoring only applies once a program
    clears all of these.
    """
    if student.qualification.strip().lower() != program.required_qualification.strip().lower():
        return "qualification_mismatch"

    if program.seats_available is not None and program.seats_available <= 0:
        return "no_seats_available"

    if (
        student.budget_max_usd is not None
        and program.annual_tuition_fee_usd is not None
        and program.annual_tuition_fee_usd > student.budget_max_usd
    ):
        return "exceeds_budget"

    if (
        program.min_english_test_score is not None
        and student.english_test_score is not None
        and student.english_test_score < program.min_english_test_score
    ):
        return "english_score_below_minimum"

    return None


def is_eligible(student: StudentProfile, program: UniversityProgram) -> bool:
    return ineligibility_reason(student, program) is None


def score_student_against_program(
    student: StudentProfile, program: UniversityProgram
) -> ScoreResult:
    """
    Returns a ScoreResult with eligible flag, final score, and a breakdown
    dict so the score is explainable (each component visible), not a black box.
    """
    reason = ineligibility_reason(student, program)
    if reason is not None:
        return ScoreResult(
            university_id=program.id,
            eligible=False,
            score=0.0,
            breakdown={"reason": reason},
        )

    academic_pct = normalized_academic_percentage(student)
    marks_ratio = academic_pct / program.min_marks_percentage_cutoff
    marks_ratio_capped = min(marks_ratio, MARKS_RATIO_CAP)

    course_match = 1.0 if student.preferred_course.strip().lower() == program.program_name.strip().lower() else 0.0
    country_match = 1.0 if student.preferred_country.strip().lower() == program.country.strip().lower() else 0.0

    weighted_marks = SCORING_WEIGHTS["marks_ratio"] * marks_ratio_capped
    weighted_course = SCORING_WEIGHTS["course_match"] * course_match
    weighted_country = SCORING_WEIGHTS["country_match"] * country_match

    final_score = weighted_marks + weighted_course + weighted_country

    # Budget headroom is informational only (not scored) — eligibility already
    # hard-filters anything over budget; this just tells the explanation
    # generator how much headroom the student has, if relevant.
    budget_headroom_usd = None
    if student.budget_max_usd is not None and program.annual_tuition_fee_usd is not None:
        budget_headroom_usd = round(student.budget_max_usd - program.annual_tuition_fee_usd, 2)

    return ScoreResult(
        university_id=program.id,
        eligible=True,
        score=round(final_score, 4),
        breakdown={
            "academic_percentage_equivalent": round(academic_pct, 2),
            "marks_ratio": round(marks_ratio_capped, 4),
            "marks_ratio_weighted": round(weighted_marks, 4),
            "course_match": bool(course_match),
            "course_match_weighted": round(weighted_course, 4),
            "country_match": bool(country_match),
            "country_match_weighted": round(weighted_country, 4),
            "tuition_fee_usd": program.annual_tuition_fee_usd,
            "budget_headroom_usd": budget_headroom_usd,
            "seats_available": program.seats_available,
        },
    )


def rank_top_n(
    student: StudentProfile,
    programs: list[UniversityProgram],
    n: int = 3,
) -> list[ScoreResult]:
    """Score student against every program, filter to eligible only,
    and return the top-n by score descending."""
    results = [score_student_against_program(student, p) for p in programs]
    eligible_results = [r for r in results if r.eligible]
    eligible_results.sort(key=lambda r: r.score, reverse=True)
    return eligible_results[:n]
