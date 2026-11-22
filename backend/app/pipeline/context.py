"""One canonical description of the student for every model prompt."""

from __future__ import annotations


def student_sentence(profile: object) -> str:
    """Describe the student's current year, program and school.

    Year of study always means the student's CURRENT year of a university or
    college program. The same sentence is used by the planner, the page selector
    and the extractor so the three stages cannot disagree about it.
    """

    year = str(getattr(profile, "year", "") or "").strip()
    program = str(getattr(profile, "field", "") or "").strip()
    school = str(getattr(profile, "school", "") or "").strip()
    current_year = f"{year} year" if year else "an undergraduate year"
    program_text = program or "undergraduate"
    school_text = school or "their university"
    return (
        f"The student is currently in {current_year} of an undergraduate {program_text} "
        f"program at {school_text}. They are not a high-school student and not an applicant."
    )
