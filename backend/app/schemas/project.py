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
            "description": "Renovate my 3x4m bathroom with walk-in shower and new tiles",
            "images": ["https://example.com/bathroom-ref.jpg"]
        }
    """

    description: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Detailed project description - include dimensions, materials, and requirements",
        examples=[
            "Renovate my 3x4m bathroom with walk-in shower, ceramic tiles, and modern fixtures",
            "Build a 6x12m infinity pool with glass mosaic tiles and integrated jacuzzi",
        ],
    )
    images: list[HttpUrl | str] = Field(
        default_factory=list,
        max_length=10,
        description="URLs of reference images or design plans",
    )
    # Kept for backward compatibility but not required in UI
    project_type: ProjectType | None = Field(
        default=None,
        description="Optional project type - will be inferred from description if not provided",
    )
    location: str = Field(
        default="Bali",
        max_length=200,
        description="Project location (defaults to Bali)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "description": "Renovate my 3x4m bathroom with walk-in shower, ceramic tiles, and modern fixtures",
                "images": ["https://example.com/bathroom-ref.jpg"],
            }
        }
