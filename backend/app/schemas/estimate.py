"""
Cost estimation schemas for BOM (Bill of Materials) and estimates
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class EstimateStatus(str, Enum):
    """Status of cost estimation request"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class BOMItem(BaseModel):
    """
    Single Bill of Materials item with pricing and metadata

    Attributes:
        material_name: Indonesian name for Tokopedia search (e.g., 'Semen 50kg')
        english_name: English name for user display (e.g., 'Cement 50kg')
        quantity: Amount needed
        unit: Unit of measurement (e.g., 'm2', 'pcs', 'kg')
        unit_price_idr: Price per unit in Indonesian Rupiah
        total_price_idr: Total cost (quantity × unit_price_idr)
        source: Where price data came from ('tokopedia', 'historical', 'estimated')
        confidence: Confidence score for pricing (0.0-1.0)
        marketplace_url: Optional link to product on marketplace
    """

    material_name: str = Field(..., description="Indonesian material name for marketplace search")
    english_name: str | None = Field(None, description="English material name for user display")
    quantity: float = Field(..., gt=0, description="Quantity needed")
    unit: str = Field(..., description="Unit of measurement", examples=["m2", "pcs", "kg", "liter"])
    unit_price_idr: int = Field(..., ge=0, description="Price per unit in IDR")
    total_price_idr: int = Field(..., ge=0, description="Total cost in IDR")
    source: str = Field(
        ...,
        description="Data source",
        examples=["tokopedia", "historical", "estimated"],
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Price confidence score")
    marketplace_url: str | None = Field(None, description="Product URL if available")
    affiliate_url: str | None = Field(
        None, description="Product URL with affiliate tracking for monetization"
    )


class EstimateResponse(BaseModel):
    """
    Complete cost estimation response with BOM breakdown

    Attributes:
        estimate_id: Unique identifier for this estimate
        status: Current processing status
        project_type: Type of construction project
        bom_items: List of materials and costs
        total_cost_idr: Sum of all BOM item costs
        labor_cost_idr: Estimated labor costs
        grand_total_idr: Total project cost including labor
        created_at: Timestamp of estimate creation
        updated_at: Last update timestamp
        error_message: Error details if status is 'failed'
    """

    estimate_id: str = Field(..., description="Unique estimate identifier")
    status: EstimateStatus = Field(..., description="Processing status")
    project_type: str = Field(..., description="Type of project")
    bom_items: list[BOMItem] = Field(
        default_factory=list, description="Bill of materials breakdown"
    )
    total_cost_idr: int = Field(default=0, ge=0, description="Total material cost")
    labor_cost_idr: int = Field(default=0, ge=0, description="Estimated labor cost")
    grand_total_idr: int = Field(default=0, ge=0, description="Total project cost")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    error_message: str | None = Field(None, description="Error details if failed")

    class Config:
        json_schema_extra = {
            "example": {
                "estimate_id": "est_abc123",
                "status": "completed",
                "project_type": "bathroom_renovation",
                "bom_items": [
                    {
                        "material_name": "Keramik 40x40",
                        "english_name": "Ceramic Tiles 40x40cm",
                        "quantity": 25.0,
                        "unit": "m2",
                        "unit_price_idr": 150000,
                        "total_price_idr": 3750000,
                        "source": "tokopedia",
                        "confidence": 0.95,
                        "marketplace_url": "https://tokopedia.com/...",
                        "affiliate_url": "https://tokopedia.com/...?extParam=aff_id%3D...",
                    }
                ],
                "total_cost_idr": 15000000,
                "labor_cost_idr": 5000000,
                "grand_total_idr": 20000000,
                "created_at": "2025-11-25T10:00:00Z",
                "updated_at": "2025-11-25T10:05:00Z",
            }
        }


class EstimateStatusResponse(BaseModel):
    """Response for estimate status check"""

    estimate_id: str
    status: EstimateStatus
    progress_percentage: int = Field(ge=0, le=100, description="Completion percentage")
    message: str | None = Field(None, description="Status message")


# =============================================================================
# Direct Price Lookup Schemas (for quick product searches)
# =============================================================================


class PriceLookupRequest(BaseModel):
    """
    Single material price lookup request.

    For quick searches like "How much is gypsum board per m²?"

    Attributes:
        material_name: Product to search (e.g., "gypsum board", "tempered glass 8mm")
        quantity: Amount needed (default: 1 for unit price)
        unit: Unit of measurement (default: "pcs")
    """

    material_name: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Material/product name to search",
        examples=["gypsum board", "tempered glass 8mm", "semen 50kg"],
    )
    quantity: float = Field(
        default=1.0,
        gt=0,
        le=10000,
        description="Quantity needed (default: 1 for unit price lookup)",
    )
    unit: str = Field(
        default="pcs",
        description="Unit of measurement",
        examples=["m2", "pcs", "kg", "liter", "meter"],
    )


class PriceLookupResponse(BaseModel):
    """
    Price lookup response with pricing data and source info.

    Includes confidence score and marketplace link for verification.
    """

    material_name: str = Field(..., description="Searched material name")
    unit_price_idr: int = Field(..., ge=0, description="Price per unit in IDR")
    total_price_idr: int = Field(..., ge=0, description="Total cost for requested quantity")
    quantity: float = Field(..., description="Requested quantity")
    unit: str = Field(..., description="Unit of measurement")
    source: str = Field(
        ...,
        description="Data source: 'cached', 'tokopedia', or 'estimated'",
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Price confidence score")
    marketplace_url: str | None = Field(None, description="Link to product on marketplace")
    affiliate_url: str | None = Field(None, description="Affiliate link for monetization")

    class Config:
        json_schema_extra = {
            "example": {
                "material_name": "Gypsum Board 9mm",
                "unit_price_idr": 85000,
                "total_price_idr": 850000,
                "quantity": 10.0,
                "unit": "m2",
                "source": "tokopedia",
                "confidence": 0.85,
                "marketplace_url": "https://tokopedia.com/...",
                "affiliate_url": "https://tokopedia.com/...?extParam=aff_id%3D...",
            }
        }


class BatchPriceLookupRequest(BaseModel):
    """
    Batch price lookup for multiple materials at once.

    Useful for users who have a list of specific materials they want priced.
    Limited to 20 items to prevent abuse and manage Apify costs.
    """

    materials: list[PriceLookupRequest] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="List of materials to price (max 20)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "materials": [
                    {"material_name": "gypsum board 9mm", "quantity": 10, "unit": "m2"},
                    {"material_name": "tempered glass 8mm", "quantity": 5, "unit": "m2"},
                    {"material_name": "semen 50kg", "quantity": 20, "unit": "pcs"},
                ]
            }
        }


class BatchPriceLookupResponse(BaseModel):
    """
    Batch price lookup response with individual prices and summary.
    """

    prices: list[PriceLookupResponse] = Field(..., description="Individual price results")
    total_cost_idr: int = Field(..., ge=0, description="Sum of all item costs")
    items_priced: int = Field(..., description="Number of items successfully priced")
    cache_hits: int = Field(default=0, description="Number of prices from cache (no Apify cost)")
    scrape_count: int = Field(default=0, description="Number of new Tokopedia scrapes")
