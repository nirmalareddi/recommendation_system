"""
Unit tests for the LLM explanation service's template fallback path
(no ANTHROPIC_API_KEY set in the test environment, so this never calls
out to a real API — deterministic and free to run).
"""

from app.llm.explanation_service import generate_explanations


def test_template_fallback_used_when_no_api_key():
    student = {
        "name": "Test Student",
        "academic_qualification": "Bachelor's Degree",
        "field_of_study": "Computer Science",
        "marks_percentage": 85.0,
        "cgpa": None,
        "preferred_course": "Computer Science",
        "preferred_country": "Canada",
        "budget_max_usd": 40000,
    }
    items = [
        {
            "university_id": "uni-1",
            "university_name": "Test University",
            "score": 0.95,
            "breakdown": {
                "course_match": True,
                "country_match": True,
                "academic_percentage_equivalent": 85.0,
                "tuition_fee_usd": 35000,
                "budget_headroom_usd": 5000,
                "seats_available": 20,
            },
        }
    ]

    results = generate_explanations(student, items)

    assert len(results) == 1
    assert results[0].source == "template_fallback"
    assert "Test University" in results[0].explanation
    assert results[0].explanation.strip() != ""


def test_template_fallback_handles_missing_breakdown_fields_gracefully():
    student = {"name": "Minimal Student", "academic_qualification": "Bachelor's Degree",
               "preferred_course": "CS", "preferred_country": "Canada"}
    items = [
        {
            "university_id": "uni-2",
            "university_name": "Bare Bones University",
            "score": 0.5,
            "breakdown": {},  # no fields at all — should still produce something sensible
        }
    ]
    results = generate_explanations(student, items)
    assert results[0].explanation.strip() != ""
