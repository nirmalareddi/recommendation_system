"""
Eligibility + merit scoring engine.

v3:
- Supports specific student qualifications such as B.Sc, B.Tech, B.Arch,
  M.Sc, M.Tech, etc.
- Normalizes student qualifications to a qualification level so that,
  for example, B.Tech can satisfy a university requirement of
  "Bachelor's Degree".
- Adds field-of-study matching.
- Keeps eligibility separate from merit scoring.
- Uses configurable weights from scoring/config.py.
"""

from dataclasses import dataclass
from typing import Optional

from app.scoring.config import SCORING_WEIGHTS, MARKS_RATIO_CAP
from app.config.settings import CGPA_TO_PERCENTAGE_MULTIPLIER


# ---------------------------------------------------------------------------
# Qualification normalization
# ---------------------------------------------------------------------------

QUALIFICATION_LEVELS = {
    # Bachelor's degrees
    "b.sc": "Bachelor's Degree",
    "bsc": "Bachelor's Degree",
    "b.tech": "Bachelor's Degree",
    "btech": "Bachelor's Degree",
    "b.e.": "Bachelor's Degree",
    "be": "Bachelor's Degree",
    "bca": "Bachelor's Degree",
    "bba": "Bachelor's Degree",
    "b.com": "Bachelor's Degree",
    "bcom": "Bachelor's Degree",
    "ba": "Bachelor's Degree",
    "b.arch": "Bachelor's Degree",
    "barch": "Bachelor's Degree",
    "mbbs": "Bachelor's Degree",

    # Master's degrees
    "m.sc": "Master's Degree",
    "msc": "Master's Degree",
    "m.tech": "Master's Degree",
    "mtech": "Master's Degree",
    "m.e.": "Master's Degree",
    "me": "Master's Degree",
    "mca": "Master's Degree",
    "mba": "Master's Degree",
    "m.com": "Master's Degree",
    "mcom": "Master's Degree",
    "ma": "Master's Degree",
    "m.arch": "Master's Degree",
    "march": "Master's Degree",
}


def _normalize_text(value: str) -> str:
    """Normalize text for case-insensitive comparison."""
    return " ".join(value.strip().lower().split())


def normalized_qualification_level(qualification: str) -> str:
    """
    Convert a specific qualification such as B.Tech or B.Sc into a
    standardized qualification level.

    The returned value is normalized consistently so that values such as
    "B.Sc", "B.Sc " and "Bachelor's Degree" can be compared safely.
    """
    normalized = _normalize_text(qualification)

    level = QUALIFICATION_LEVELS.get(normalized, normalized)

    return _normalize_text(level)


# ---------------------------------------------------------------------------
# Field-of-study normalization
# ---------------------------------------------------------------------------

FIELD_GROUPS = {
    "computer science": {
        "computer science",
        "computer engineering",
        "information technology",
        "information systems",
        "software engineering",
        "computing",
    },
    "business": {
        "business",
        "business administration",
        "management",
        "business analytics",
    },
    "commerce": {
        "commerce",
        "accounting",
        "finance",
        "banking",
    },
    "engineering": {
        "engineering",
        "mechanical engineering",
        "civil engineering",
        "electrical engineering",
        "electronics engineering",
        "electronics",
    },
    "architecture": {
        "architecture",
        "architectural studies",
        "urban planning",
        "urban design",
    },
    "biology": {
        "biology",
        "biological sciences",
        "biomedical science",
        "biomedical sciences",
    },
    "biotechnology": {
        "biotechnology",
        "bio technology",
    },
    "health sciences": {
        "health sciences",
        "public health",
        "healthcare",
        "nursing",
    },
    "economics": {
        "economics",
        "economics and finance",
    },
    "design": {
        "design",
        "ux design",
        "ui design",
        "ux/ui design",
        "interaction design",
        "industrial design",
    },
}


def normalized_field_group(field_of_study: str) -> str:
    """
    Map a field of study into a broader related-field group.

    Exact field matches are handled separately. This function allows
    closely related academic backgrounds to receive a partial match.
    """
    normalized = _normalize_text(field_of_study)

    for group, fields in FIELD_GROUPS.items():
        if normalized in fields:
            return group

    return normalized


def field_of_study_match(student_field: str, program_field: str) -> float:
    """
    Return field-of-study compatibility:

        1.0 = exact match
        0.5 = related field group
        0.0 = unrelated field
    """
    student_normalized = _normalize_text(student_field)
    program_normalized = _normalize_text(program_field)

    if student_normalized == program_normalized:
        return 1.0

    if normalized_field_group(student_field) == normalized_field_group(program_field):
        return 0.5

    return 0.0


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class StudentProfile:
    qualification: str
    field_of_study: str
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
    field_of_study: Optional[str]
    degree_level: Optional[str]
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


# ---------------------------------------------------------------------------
# Academic normalization
# ---------------------------------------------------------------------------

def normalized_academic_percentage(student: StudentProfile) -> float:
    """
    Return the student's academic score as a percentage-equivalent.

    If both percentage and CGPA are provided, percentage takes precedence.

    If only CGPA is provided, it is converted using the configured
    CGPA_TO_PERCENTAGE_MULTIPLIER. This is an approximation and should
    not be treated as an institution-specific official conversion.
    """
    if student.marks_percentage is not None:
        return student.marks_percentage

    if student.cgpa is not None:
        return student.cgpa * CGPA_TO_PERCENTAGE_MULTIPLIER

    raise ValueError(
        "Student profile has neither marks_percentage nor cgpa set"
    )


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------

def ineligibility_reason(
    student: StudentProfile,
    program: UniversityProgram,
) -> Optional[str]:
    """
    Hard eligibility filters.

    These are pass/fail gates. Merit scoring is only applied after the
    program passes all eligibility checks.
    """

    # Qualification-level eligibility
    student_level = normalized_qualification_level(student.qualification)
    required_level = normalized_qualification_level(
        program.required_qualification
    )

    if student_level != required_level:
        return "qualification_mismatch"

    # Seat availability
    if (
        program.seats_available is not None
        and program.seats_available <= 0
    ):
        return "no_seats_available"

    # Budget
    if (
        student.budget_max_usd is not None
        and program.annual_tuition_fee_usd is not None
        and program.annual_tuition_fee_usd > student.budget_max_usd
    ):
        return "exceeds_budget"

    # English requirement
    if (
        program.min_english_test_score is not None
        and student.english_test_score is not None
        and student.english_test_score < program.min_english_test_score
    ):
        return "english_score_below_minimum"

    # Academic cutoff
    academic_pct = normalized_academic_percentage(student)

    if academic_pct < program.min_marks_percentage_cutoff:
        return "academic_cutoff_not_met"

    return None


def is_eligible(
    student: StudentProfile,
    program: UniversityProgram,
) -> bool:
    return ineligibility_reason(student, program) is None


# ---------------------------------------------------------------------------
# Merit scoring
# ---------------------------------------------------------------------------

def score_student_against_program(
    student: StudentProfile,
    program: UniversityProgram,
) -> ScoreResult:
    """
    Score an eligible student against a university program.

    The final score is composed of:

        Academic fit       40%
        Course match       25%
        Field-of-study     20%
        Country match      15%

    Eligibility criteria such as budget, English score, seats and academic
    cutoff remain hard filters rather than partial-score components.
    """

    reason = ineligibility_reason(student, program)

    if reason is not None:
        return ScoreResult(
            university_id=program.id,
            eligible=False,
            score=0.0,
            breakdown={
                "reason": reason,
            },
        )

    # Academic fit
    academic_pct = normalized_academic_percentage(student)

    marks_ratio = (
        academic_pct / program.min_marks_percentage_cutoff
    )

    marks_ratio_capped = min(
        marks_ratio,
        MARKS_RATIO_CAP,
    )

    # Course match
    course_match = (
        1.0
        if _normalize_text(student.preferred_course)
        == _normalize_text(program.program_name)
        else 0.0
    )

    # Field-of-study match
    program_field = program.field_of_study or ""

    study_match = field_of_study_match(
        student.field_of_study,
        program_field,
    )

    # Country match
    country_match = (
        1.0
        if _normalize_text(student.preferred_country)
        == _normalize_text(program.country)
        else 0.0
    )

    # Weighted components
    weighted_marks = (
        SCORING_WEIGHTS["marks_ratio"]
        * marks_ratio_capped
    )

    weighted_course = (
        SCORING_WEIGHTS["course_match"]
        * course_match
    )

    weighted_field = (
        SCORING_WEIGHTS["field_of_study_match"]
        * study_match
    )

    weighted_country = (
        SCORING_WEIGHTS["country_match"]
        * country_match
    )

    final_score = (
        weighted_marks
        + weighted_course
        + weighted_field
        + weighted_country
    )

    # Keep the final user-facing score within the 0-1 range.
    # Normalize the score to a 0-1 range while preserving
    # differences between recommendations.
    max_possible_score = (
        SCORING_WEIGHTS["marks_ratio"] * MARKS_RATIO_CAP
        + SCORING_WEIGHTS["course_match"]
        + SCORING_WEIGHTS["field_of_study_match"]
        + SCORING_WEIGHTS["country_match"]
    )

    final_score = min(
        final_score / max_possible_score,
        1.0,
    )

    # Budget headroom is informational only.
    budget_headroom_usd = None

    if (
        student.budget_max_usd is not None
        and program.annual_tuition_fee_usd is not None
    ):
        budget_headroom_usd = round(
            student.budget_max_usd
            - program.annual_tuition_fee_usd,
            2,
        )

    return ScoreResult(
        university_id=program.id,
        eligible=True,
        score=round(final_score, 4),
        breakdown={
            "academic_percentage_equivalent": round(
                academic_pct,
                2,
            ),
            "marks_ratio": round(
                marks_ratio_capped,
                4,
            ),
            "marks_ratio_weighted": round(
                weighted_marks,
                4,
            ),
            "course_match": bool(course_match),
            "course_match_weighted": round(
                weighted_course,
                4,
            ),
            "field_of_study_match": round(
                study_match,
                4,
            ),
            "field_of_study_match_weighted": round(
                weighted_field,
                4,
            ),
            "country_match": bool(country_match),
            "country_match_weighted": round(
                weighted_country,
                4,
            ),
            "tuition_fee_usd": program.annual_tuition_fee_usd,
            "budget_headroom_usd": budget_headroom_usd,
            "seats_available": program.seats_available,
            "min_english_test_score": program.min_english_test_score,
            "academic_cutoff": program.min_marks_percentage_cutoff,
        },
    )


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def rank_top_n(
    student: StudentProfile,
    programs: list[UniversityProgram],
    n: int = 3,
) -> list[ScoreResult]:
    """
    Score every program, remove ineligible programs, and return the
    top-n eligible programs sorted by score descending.
    """

    results = [
        score_student_against_program(student, program)
        for program in programs
    ]

    eligible_results = [
        result
        for result in results
        if result.eligible
    ]

    eligible_results.sort(
        key=lambda result: result.score,
        reverse=True,
    )

    return eligible_results[:n]