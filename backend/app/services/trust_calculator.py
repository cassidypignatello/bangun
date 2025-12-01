"""
Trust score calculation for workers and contractors based on scraped data sources.

New algorithm (100-point scale):
- Source tier: 30 points (OLX=9, Google Maps=24, Manual=30)
- Reviews: 25 points (0, 1-5, 6-20, 21-50, 51-100, 100+)
- Rating: 20 points (4.5-5.0→20, 4.0-4.4→16, 3.5-3.9→10)
- Verification: 15 points (Photos+5, Website+3, WhatsApp+3, Platform jobs+4)
- Freshness: 10 points (Active <7d→10, <30d→7, <90d→4)
"""

from datetime import datetime, timedelta
from enum import Enum

from app.schemas.worker import TrustScoreDetailed, TrustLevel


class SourceTier(str, Enum):
    """Source tier for worker data quality"""

    GOOGLE_MAPS = "google_maps"  # Highest trust - 24 points
    MANUAL_CURATED = "manual"  # Manual verification - 30 points
    OLX = "olx"  # Lowest trust - 9 points
    PLATFORM = "platform"  # Our platform data - 30 points


# Scoring weights (total: 100 points)
WEIGHTS = {
    "source_base": 30,  # Base points from source tier
    "reviews": 25,  # Review count scoring
    "rating": 20,  # Rating quality
    "verification": 15,  # Verification signals
    "freshness": 10,  # Listing recency
}

# Source tier base scores
SOURCE_SCORES = {
    SourceTier.PLATFORM: 30,
    SourceTier.MANUAL_CURATED: 30,
    SourceTier.GOOGLE_MAPS: 24,
    SourceTier.OLX: 9,
}

# Review count brackets
REVIEW_BRACKETS = [
    (100, 25),  # 100+ reviews → 25 points
    (51, 22),  # 51-100 reviews → 22 points
    (21, 18),  # 21-50 reviews → 18 points
    (6, 12),  # 6-20 reviews → 12 points
    (1, 6),  # 1-5 reviews → 6 points
    (0, 0),  # 0 reviews → 0 points
]


def calculate_source_score(source: SourceTier) -> int:
    """
    Calculate base score from source tier.

    Args:
        source: Data source tier

    Returns:
        int: Base score (9-30 points)
    """
    return SOURCE_SCORES.get(source, 0)


def calculate_review_score(review_count: int) -> int:
    """
    Calculate score from review count.

    Brackets:
    - 100+ reviews → 25 points
    - 51-100 → 22 points
    - 21-50 → 18 points
    - 6-20 → 12 points
    - 1-5 → 6 points
    - 0 → 0 points

    Args:
        review_count: Number of reviews

    Returns:
        int: Review score (0-25 points)
    """
    for threshold, score in REVIEW_BRACKETS:
        if review_count >= threshold:
            return score
    return 0


def calculate_rating_score(rating: float | None) -> int:
    """
    Calculate score from rating quality.

    Ranges:
    - 4.5-5.0 → 20 points
    - 4.0-4.4 → 16 points
    - 3.5-3.9 → 10 points
    - 3.0-3.4 → 5 points
    - <3.0 → 0 points

    Args:
        rating: Average rating (0.0-5.0)

    Returns:
        int: Rating score (0-20 points)
    """
    if rating is None or rating < 3.0:
        return 0
    elif rating >= 4.5:
        return 20
    elif rating >= 4.0:
        return 16
    elif rating >= 3.5:
        return 10
    else:
        return 5


def calculate_verification_score(
    photos_count: int,
    has_website: bool,
    has_whatsapp: bool,
    platform_jobs: int,
) -> int:
    """
    Calculate score from verification signals.

    Components:
    - Photos: 5 points (if >0)
    - Website: 3 points
    - WhatsApp: 3 points
    - Platform jobs: 4 points (if >0)

    Args:
        photos_count: Number of photos
        has_website: Has website URL
        has_whatsapp: Has WhatsApp number
        platform_jobs: Completed jobs on our platform

    Returns:
        int: Verification score (0-15 points)
    """
    score = 0

    if photos_count > 0:
        score += 5

    if has_website:
        score += 3

    if has_whatsapp:
        score += 3

    if platform_jobs > 0:
        score += 4

    return min(score, 15)  # Cap at 15 points


def calculate_freshness_score(
    last_active: datetime | None, listing_age_days: int | None
) -> int:
    """
    Calculate score from listing freshness.

    Brackets:
    - Active <7 days → 10 points
    - Active <30 days → 7 points
    - Active <90 days → 4 points
    - Older → 0 points

    Args:
        last_active: Last activity timestamp
        listing_age_days: Days since listing created (for OLX)

    Returns:
        int: Freshness score (0-10 points)
    """
    # Use last_active if available, otherwise use listing age
    if last_active:
        age_days = (datetime.utcnow() - last_active).days
    elif listing_age_days is not None:
        age_days = listing_age_days
    else:
        return 0  # No freshness data

    if age_days < 7:
        return 10
    elif age_days < 30:
        return 7
    elif age_days < 90:
        return 4
    else:
        return 0


def determine_trust_level(total_score: int) -> TrustLevel:
    """
    Determine trust level badge from total score.

    Levels:
    - VERIFIED: ≥80 points (Top tier, Google Maps with many reviews)
    - HIGH: 60-79 points (Solid contractors, good reviews)
    - MEDIUM: 40-59 points (Acceptable, basic verification)
    - LOW: <40 points (Risky, filter out from display)

    Args:
        total_score: Total trust score (0-100)

    Returns:
        TrustLevel: Trust level badge
    """
    if total_score >= 80:
        return TrustLevel.VERIFIED
    elif total_score >= 60:
        return TrustLevel.HIGH
    elif total_score >= 40:
        return TrustLevel.MEDIUM
    else:
        return TrustLevel.LOW


def calculate_trust_score(
    source: SourceTier,
    review_count: int = 0,
    rating: float | None = None,
    photos_count: int = 0,
    has_website: bool = False,
    has_whatsapp: bool = False,
    platform_jobs: int = 0,
    last_active: datetime | None = None,
    listing_age_days: int | None = None,
) -> TrustScoreDetailed:
    """
    Calculate comprehensive trust score for a worker.

    Args:
        source: Data source tier
        review_count: Number of reviews (Google Maps)
        rating: Average rating (0.0-5.0)
        photos_count: Number of photos available
        has_website: Has website URL
        has_whatsapp: Has WhatsApp contact
        platform_jobs: Completed jobs on our platform
        last_active: Last activity timestamp
        listing_age_days: Days since listing created (OLX)

    Returns:
        TrustScoreDetailed: Detailed trust score with breakdown
    """
    source_score = calculate_source_score(source)
    reviews_score = calculate_review_score(review_count)
    rating_score = calculate_rating_score(rating)
    verification_score = calculate_verification_score(
        photos_count, has_website, has_whatsapp, platform_jobs
    )
    freshness_score = calculate_freshness_score(last_active, listing_age_days)

    total_score = (
        source_score
        + reviews_score
        + rating_score
        + verification_score
        + freshness_score
    )

    trust_level = determine_trust_level(total_score)

    return TrustScoreDetailed(
        total_score=total_score,
        trust_level=trust_level,
        breakdown={
            "source": source_score,
            "reviews": reviews_score,
            "rating": rating_score,
            "verification": verification_score,
            "freshness": freshness_score,
        },
        source_tier=source,
        review_count=review_count,
        rating=rating,
    )


def mask_worker_name(full_name: str) -> str:
    """
    Mask worker name for preview (before unlock).

    Examples:
        "Ahmad Suryanto" -> "A████ S████"
        "John Doe" -> "J███ D███"
        "Wayan" -> "W████"
        "Pak Wayan's Pool Service" -> "P██ W████'s Pool Service"

    Args:
        full_name: Complete worker name or business name

    Returns:
        str: Masked name with preserved structure
    """
    if not full_name:
        return "Unknown"

    parts = full_name.strip().split()

    if len(parts) == 1:
        # Single name - show first char, mask rest
        return f"{parts[0][0]}{'█' * min(len(parts[0]) - 1, 4)}"

    # Multiple names - mask each word except special characters
    masked_parts = []
    for part in parts:
        # Skip short connector words (of, &, etc.)
        if len(part) <= 2 and not part[0].isupper():
            masked_parts.append(part)
        else:
            # Mask word: show first char, hide rest
            masked_parts.append(f"{part[0]}{'█' * min(len(part) - 1, 3)}")

    return " ".join(masked_parts)


def mask_phone_number(phone: str) -> str:
    """
    Mask phone number for preview.

    Examples:
        "+62812345678" -> "+628████5678"
        "081234567890" -> "0812████7890"

    Args:
        phone: Complete phone number

    Returns:
        str: Masked phone number (show first 4 and last 4 digits)
    """
    if not phone or len(phone) < 8:
        return "***"

    # Remove spaces and formatting
    clean = phone.replace(" ", "").replace("-", "")

    if len(clean) <= 8:
        return f"{clean[:2]}████{clean[-2:]}"

    return f"{clean[:4]}████{clean[-4:]}"
