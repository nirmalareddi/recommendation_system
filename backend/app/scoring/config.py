"""
Tunable scoring configuration.
Keep weights here (not hardcoded in scoring.py) so they can be adjusted
during POC calibration without touching logic code.
"""

SCORING_WEIGHTS = {
    "marks_ratio": 0.5,     # how much (student_marks / cutoff_marks) counts
    "course_match": 0.3,    # how much preferred-course match counts
    "country_match": 0.2,   # how much preferred-country match counts
}

# Marks/CGPA ratio is capped at this value so a student far above cutoff
# doesn't blow out the score (e.g., cap at 1.2 = 120% of cutoff counts as max credit)
MARKS_RATIO_CAP = 1.2
