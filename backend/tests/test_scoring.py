"""
Unit tests for the scoring engine (Stage C), including v2 additions:
CGPA normalization, budget, seats, and English score eligibility filters.
"""

import pytest

from app.scoring.scoring import (
    StudentProfile,
    UniversityProgram,
    score_student_against_program,
    rank_top_n,
    normalized_academic_percentage,
)
from app.scoring.config import SCORING_WEIGHTS, MARKS_RATIO_CAP
from app.config.settings import CGPA_TO_PERCENTAGE_MULTIPLIER


def make_student(**overrides):
    defaults = dict(
        qualification="Bachelor's Degree",
        marks_percentage=85.0,
        preferred_course="Computer Science",
        preferred_country="Canada",
    )
    defaults.update(overrides)
    return StudentProfile(**defaults)


def make_program(**overrides):
    defaults = dict(
        id="uni-1",
        name="Sample University",
        country="Canada",
        program_name="Computer Science",
        required_qualification="Bachelor's Degree",
        min_marks_percentage_cutoff=70.0,
    )
    defaults.update(overrides)
    return UniversityProgram(**defaults)


# --- Eligibility gates ---

def test_ineligible_when_qualification_mismatch():
    student = make_student(qualification="High School Diploma")
    program = make_program()
    result = score_student_against_program(student, program)
    assert result.eligible is False
    assert result.breakdown["reason"] == "qualification_mismatch"


def test_ineligible_when_no_seats_available():
    student = make_student()
    program = make_program(seats_available=0)
    result = score_student_against_program(student, program)
    assert result.eligible is False
    assert result.breakdown["reason"] == "no_seats_available"


def test_eligible_when_seats_not_tracked():
    student = make_student()
    program = make_program(seats_available=None)
    result = score_student_against_program(student, program)
    assert result.eligible is True


def test_ineligible_when_exceeds_budget():
    student = make_student(budget_max_usd=20000)
    program = make_program(annual_tuition_fee_usd=45000)
    result = score_student_against_program(student, program)
    assert result.eligible is False
    assert result.breakdown["reason"] == "exceeds_budget"


def test_eligible_when_within_budget():
    student = make_student(budget_max_usd=50000)
    program = make_program(annual_tuition_fee_usd=45000)
    result = score_student_against_program(student, program)
    assert result.eligible is True
    assert result.breakdown["budget_headroom_usd"] == 5000


def test_ineligible_when_english_score_below_minimum():
    student = make_student(english_test_score=5.5)
    program = make_program(min_english_test_score=6.5)
    result = score_student_against_program(student, program)
    assert result.eligible is False
    assert result.breakdown["reason"] == "english_score_below_minimum"


# --- CGPA normalization ---

def test_normalized_academic_percentage_prefers_marks_percentage():
    student = make_student(marks_percentage=88.0, cgpa=9.0)
    assert normalized_academic_percentage(student) == 88.0


def test_normalized_academic_percentage_uses_cgpa_when_no_marks():
    student = make_student(marks_percentage=None, cgpa=8.0)
    expected = 8.0 * CGPA_TO_PERCENTAGE_MULTIPLIER
    assert normalized_academic_percentage(student) == expected


def test_cgpa_only_student_scores_against_percentage_cutoff():
    student = make_student(marks_percentage=None, cgpa=8.5)  # -> 80.75%
    program = make_program(min_marks_percentage_cutoff=70.0)
    result = score_student_against_program(student, program)
    assert result.eligible is True
    assert result.breakdown["academic_percentage_equivalent"] == 80.75


# --- Scoring ---

def test_full_match_scores_highest():
    student = make_student()
    program = make_program()
    result = score_student_against_program(student, program)
    assert result.eligible is True
    assert result.breakdown["course_match"] is True
    assert result.breakdown["country_match"] is True
    assert result.score > 0.8


def test_partial_match_scores_lower_than_full_match():
    student = make_student()
    program_full = make_program()
    program_partial = make_program(id="uni-2", country="Germany")

    full_result = score_student_against_program(student, program_full)
    partial_result = score_student_against_program(student, program_partial)

    assert full_result.score > partial_result.score


def test_marks_ratio_is_capped():
    student = make_student(marks_percentage=100.0)
    program = make_program(min_marks_percentage_cutoff=50.0)  # ratio would be 2.0 uncapped
    result = score_student_against_program(student, program)
    max_possible = (
        MARKS_RATIO_CAP * SCORING_WEIGHTS["marks_ratio"]
        + SCORING_WEIGHTS["course_match"]
        + SCORING_WEIGHTS["country_match"]
    )
    assert result.score <= max_possible + 0.0001


def test_rank_top_n_returns_sorted_eligible_only():
    student = make_student()
    programs = [
        make_program(id="uni-1", country="Canada"),
        make_program(id="uni-2", country="Germany"),
        make_program(id="uni-3", required_qualification="PhD"),
        make_program(id="uni-4", seats_available=0),
    ]
    top = rank_top_n(student, programs, n=3)
    assert len(top) == 2
    assert top[0].university_id == "uni-1"
    assert top[0].score >= top[1].score
