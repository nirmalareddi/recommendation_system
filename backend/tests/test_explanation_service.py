"""
Tests for the recommendation explanation service.

The fallback test explicitly disables the Anthropic API key so the test
does not depend on whatever environment variables happen to be configured
on the developer's machine.
"""

from app.llm.explanation_service import generate_explanations


def test_template_fallback_used_when_no_api_key(monkeypatch):
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
                "field_of_study_match": 1.0,
                "academic_percentage_equivalent": 85.0,
                "tuition_fee_usd": 35000,
                "budget_headroom_usd": 5000,
                "seats_available": 20,
            },
        }
    ]

    # Explicitly disable the API key for this test.
    monkeypatch.setattr(
        "app.llm.explanation_service.ANTHROPIC_API_KEY",
        None,
    )

    results = generate_explanations(student, items)

    assert len(results) == 1
    assert results[0].source == "template_fallback"
    assert results[0].university_id == "uni-1"
    assert results[0].explanation
    assert isinstance(results[0].explanation, str)


def test_explanation_contains_university_name():
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
                "field_of_study_match": 1.0,
                "academic_percentage_equivalent": 85.0,
                "tuition_fee_usd": 35000,
                "budget_headroom_usd": 5000,
                "seats_available": 20,
            },
        }
    ]

    results = generate_explanations(student, items)

    assert len(results) == 1
    assert results[0].explanation
    assert "Test University" in results[0].explanation