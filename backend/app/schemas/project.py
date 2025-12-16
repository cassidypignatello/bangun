"""
Project-related Pydantic schemas for input validation
"""

from enum import Enum

from pydantic import BaseModel, Field, HttpUrl


class ProjectType(str, Enum):
    """Supported project types for cost estimation"""

    VILLA_CONSTRUCTION = "villa_construction"
    HOME_RENOVATION = "home_renovation"
    BATHROOM_RENOVATION = "bathroom_renovation"
    KITCHEN_RENOVATION = "kitchen_renovation"
    POOL_CONSTRUCTION = "pool_construction"
    EXTENSION = "extension"


class ProjectInput(BaseModel):
    """
    Input schema for construction project estimation

    Example:
        {
            "project_type": "villa_construction",
            "description": "3-bedroom villa with pool, 200m2",
            "images": ["https://example.com/image1.jpg"],
            "location": "Canggu, Bali"
        }
    """

    project_type: ProjectType = Field(
        ..., description="Type of construction or renovation project"
    )
    description: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Detailed project description",
        examples=["Modern 3-bedroom villa with infinity pool, 200m2, minimalist design"],
    )
    images: list[HttpUrl | str] = Field(
        default_factory=list,
        max_length=10,
        description="URLs of reference images or design plans",
    )
    location: str = Field(
        default="Bali",
        max_length=200,
        description="Project location in Bali",
        examples=["Canggu", "Ubud", "Seminyak"],
    )

    class Config:
        json_schema_extra = {
            "example": {
                "project_type": "villa_construction",
                "description": "Modern 3-bedroom villa with infinity pool, 200m2, tropical design",
                "images": [
                    "https://example.com/villa-front.jpg",
                    "https://example.com/villa-pool.jpg",
                ],
                "location": "Canggu, Bali",
            }
        }
