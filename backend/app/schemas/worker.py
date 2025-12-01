"""
Worker and contractor schemas with trust scoring for scraped data sources
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl


class TrustLevel(str, Enum):
    """Trust level badges based on total score"""

    VERIFIED = "VERIFIED"  # ≥80 points
    HIGH = "HIGH"  # 60-79 points
    MEDIUM = "MEDIUM"  # 40-59 points
    LOW = "LOW"  # <40 points


class TrustScoreDetailed(BaseModel):
    """
    Detailed trust score with breakdown (100-point scale).

    Components:
    - Source tier: 30 points (OLX=9, GMaps=24, Manual=30)
    - Reviews: 25 points (based on count)
    - Rating: 20 points (based on quality)
    - Verification: 15 points (photos, website, whatsapp)
    - Freshness: 10 points (listing recency)
    """

    total_score: int = Field(..., ge=0, le=100, description="Total trust score (0-100)")
    trust_level: TrustLevel = Field(..., description="Trust level badge")
    breakdown: dict[str, int] = Field(
        ...,
        description="Score breakdown by component",
        examples=[
            {
                "source": 24,
                "reviews": 22,
                "rating": 20,
                "verification": 11,
                "freshness": 10,
            }
        ],
    )
    source_tier: str = Field(..., description="Data source tier")
    review_count: int = Field(..., ge=0, description="Number of reviews")
    rating: float | None = Field(None, ge=0.0, le=5.0, description="Average rating")

    class Config:
        json_schema_extra = {
            "example": {
                "total_score": 87,
                "trust_level": "VERIFIED",
                "breakdown": {
                    "source": 24,
                    "reviews": 22,
                    "rating": 20,
                    "verification": 11,
                    "freshness": 10,
                },
                "source_tier": "google_maps",
                "review_count": 67,
                "rating": 4.8,
            }
        }


class WorkerContact(BaseModel):
    """Worker contact information (unlocked only)"""

    phone: str | None = Field(None, description="Contact phone number")
    whatsapp: str | None = Field(None, description="WhatsApp number")
    email: str | None = Field(None, description="Contact email")
    website: str | None = Field(None, description="Business website")


class WorkerLocation(BaseModel):
    """Worker location information"""

    address: str | None = Field(None, description="Full address")
    area: str = Field(..., description="General area", examples=["Canggu", "Ubud"])
    latitude: float | None = Field(None, description="GPS latitude")
    longitude: float | None = Field(None, description="GPS longitude")
    maps_url: str | None = Field(None, description="Google Maps URL")


class WorkerReview(BaseModel):
    """Individual worker review"""

    rating: int = Field(..., ge=1, le=5, description="Review rating")
    text: str = Field(..., description="Review text")
    reviewer: str = Field(..., description="Reviewer name")
    date: str = Field(..., description="Review date")
    source: str = Field(..., description="Review source", examples=["google_maps", "platform"])


class WorkerPreview(BaseModel):
    """
    Preview of worker/contractor before unlocking full details.
    Contact information is masked until payment.
    """

    id: str = Field(..., description="Unique worker identifier")
    preview_name: str = Field(
        ..., description="Masked name for preview", examples=["P██ W████'s Pool Service"]
    )
    trust_score: TrustScoreDetailed = Field(..., description="Detailed trust scoring")
    location: str = Field(..., description="General location", examples=["Canggu", "Ubud"])
    specializations: list[str] = Field(
        ..., description="Worker specializations", examples=[["pool", "general"]]
    )

    # Preview data (limited before unlock)
    preview_review: str | None = Field(None, description="Top review excerpt")
    photos_count: int = Field(0, ge=0, description="Number of portfolio photos")
    opening_hours: str | None = Field(None, description="Business hours")

    # Pricing (if available from OLX)
    price_idr_per_day: int | None = Field(None, ge=0, description="Daily rate in IDR")

    # Unlock status
    contact_locked: bool = Field(True, description="Whether contact info is locked")
    unlock_price_idr: int = Field(50000, description="Unlock price in IDR")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "uuid-1234",
                "preview_name": "P██ W████'s Pool Service",
                "trust_score": {
                    "total_score": 87,
                    "trust_level": "VERIFIED",
                    "breakdown": {
                        "source": 24,
                        "reviews": 22,
                        "rating": 20,
                        "verification": 11,
                        "freshness": 10,
                    },
                    "source_tier": "google_maps",
                    "review_count": 67,
                    "rating": 4.8,
                },
                "location": "Canggu",
                "specializations": ["pool"],
                "preview_review": "Excellent pool work, finished on time - Sarah M.",
                "photos_count": 15,
                "opening_hours": "Mon-Sat 8AM-5PM",
                "price_idr_per_day": None,
                "contact_locked": True,
                "unlock_price_idr": 50000,
            }
        }


class WorkerFullDetails(BaseModel):
    """
    Full worker details after unlocking via payment.
    Includes complete contact information and reviews.
    """

    id: str = Field(..., description="Unique worker identifier")
    business_name: str = Field(..., description="Full business name")
    trust_score: TrustScoreDetailed = Field(..., description="Detailed trust scoring")

    # Contact (unlocked)
    contact: WorkerContact = Field(..., description="Contact information")

    # Location
    location: WorkerLocation = Field(..., description="Location details")

    # Reviews
    reviews: list[WorkerReview] = Field(
        default_factory=list, description="Customer reviews", max_length=10
    )

    # Additional details
    specializations: list[str] = Field(..., description="Worker specializations")
    photos_count: int = Field(0, ge=0, description="Number of portfolio photos")
    opening_hours: str | None = Field(None, description="Business hours")
    categories: list[str] = Field(
        default_factory=list, description="Business categories"
    )

    # Pricing
    price_idr_per_day: int | None = Field(None, ge=0, description="Daily rate in IDR")

    # Negotiation assistance
    negotiation_script: str | None = Field(
        None, description="AI-generated negotiation tips based on trust score"
    )

    # Metadata
    unlocked_at: datetime = Field(..., description="When details were unlocked")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "uuid-1234",
                "business_name": "Pak Wayan's Pool Service",
                "trust_score": {
                    "total_score": 87,
                    "trust_level": "VERIFIED",
                    "breakdown": {
                        "source": 24,
                        "reviews": 22,
                        "rating": 20,
                        "verification": 11,
                        "freshness": 10,
                    },
                    "source_tier": "google_maps",
                    "review_count": 67,
                    "rating": 4.8,
                },
                "contact": {
                    "phone": "+62361234567",
                    "whatsapp": "+62812345678",
                    "email": "pakwayan@example.com",
                    "website": "https://pakwayanpool.com",
                },
                "location": {
                    "address": "Jl. Raya Canggu No. 123",
                    "area": "Canggu",
                    "latitude": -8.6500,
                    "longitude": 115.1333,
                    "maps_url": "https://maps.google.com/...",
                },
                "reviews": [
                    {
                        "rating": 5,
                        "text": "Excellent pool work, finished on time",
                        "reviewer": "Sarah M.",
                        "date": "2025-10-15",
                        "source": "google_maps",
                    }
                ],
                "specializations": ["pool"],
                "photos_count": 15,
                "opening_hours": "Mon-Sat 8AM-5PM",
                "categories": ["Pool contractor", "Construction"],
                "price_idr_per_day": None,
                "negotiation_script": "This contractor has VERIFIED status with 67 reviews. Fair price range: 500k-750k IDR/day. Tip: Ask about warranty and timeline guarantees.",
                "unlocked_at": "2025-11-30T10:30:00Z",
            }
        }


class WorkerSearchRequest(BaseModel):
    """Request schema for worker search"""

    project_type: str = Field(
        ...,
        description="Project type",
        examples=["pool_construction", "bathroom_renovation", "general"],
    )
    location: str = Field(..., description="Preferred location", examples=["Canggu", "Ubud"])
    min_trust_score: int = Field(
        40, ge=0, le=100, description="Minimum trust score filter"
    )
    budget_range: str | None = Field(
        None, description="Budget range", examples=["low", "medium", "high"]
    )
    max_results: int = Field(3, ge=1, le=10, description="Maximum results to return")


class WorkerSearchResponse(BaseModel):
    """Response schema for worker search"""

    workers: list[WorkerPreview] = Field(..., description="Worker previews")
    total_found: int = Field(..., description="Total workers found")
    showing: int = Field(..., description="Number of workers returned")
    unlock_price_idr: int = Field(50000, description="Price to unlock contact details")
    ok: bool = Field(True, description="Request success status")
