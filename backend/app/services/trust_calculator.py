"""
Trust score calculation for workers and contractors
"""

from app.schemas.worker import TrustScore


def calculate_trust_score(
    project_count: int,
    avg_rating: float,
    license_verified: bool,
    insurance_verified: bool,
    background_check: bool,
    years_experience: int,
) -> float:
    """
    Calculate composite trust score for a worker

    Weighted formula:
    - Project count: 20% (normalized to 0-1)
    - Average rating: 30% (normalized to 0-1)
    - License verified: 15%
    - Insurance verified: 15%
    - Background check: 10%
    - Years experience: 10% (normalized to 0-1)

    Args:
        project_count: Number of completed projects
        avg_rating: Average rating (0.0-5.0)
        license_verified: Professional license status
        insurance_verified: Insurance verification status
        background_check: Background check passed
        years_experience: Years of professional experience

    Returns:
        float: Composite trust score (0.0-1.0)
    """
    # Normalize project count (assume 50+ projects is max)
    project_score = min(project_count / 50.0, 1.0) * 0.20

    # Normalize rating (5.0 is max)
    rating_score = (avg_rating / 5.0) * 0.30

    # Binary verifications
    license_score = 0.15 if license_verified else 0.0
    insurance_score = 0.15 if insurance_verified else 0.0
    background_score = 0.10 if background_check else 0.0

    # Normalize experience (assume 20+ years is max)
    experience_score = min(years_experience / 20.0, 1.0) * 0.10

    total_score = (
        project_score
        + rating_score
        + license_score
        + insurance_score
        + background_score
        + experience_score
    )

    return round(total_score, 2)


def create_trust_score(worker_data: dict) -> TrustScore:
    """
    Create TrustScore object from worker data

    Args:
        worker_data: Worker dictionary from database

    Returns:
        TrustScore: Trust score with breakdown
    """
    project_count = worker_data.get("project_count", 0)
    avg_rating = worker_data.get("avg_rating", 0.0)
    license_verified = worker_data.get("license_verified", False)
    insurance_verified = worker_data.get("insurance_verified", False)
    background_check = worker_data.get("background_check", False)
    years_experience = worker_data.get("years_experience", 0)

    overall_score = calculate_trust_score(
        project_count,
        avg_rating,
        license_verified,
        insurance_verified,
        background_check,
        years_experience,
    )

    return TrustScore(
        overall_score=overall_score,
        project_count=project_count,
        avg_rating=avg_rating,
        license_verified=license_verified,
        insurance_verified=insurance_verified,
        background_check=background_check,
        years_experience=years_experience,
    )


def mask_worker_name(full_name: str) -> str:
    """
    Mask worker name for preview (before unlock)

    Examples:
        "Ahmad Suryanto" -> "Ahmad S****"
        "John Doe" -> "John D****"
        "Wayan" -> "W****"

    Args:
        full_name: Complete worker name

    Returns:
        str: Masked name
    """
    parts = full_name.strip().split()

    if len(parts) == 1:
        # Single name - mask most of it
        return f"{parts[0][0]}****"

    # Multiple names - show first name, mask last name
    first = parts[0]
    last = parts[-1]
    return f"{first} {last[0]}****"
