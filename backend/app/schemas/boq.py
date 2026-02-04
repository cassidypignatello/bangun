"""
Pydantic schemas for BoQ (Bill of Quantity) upload and analysis.

These schemas handle:
- File upload requests
- Job status tracking
- Extracted item representation
- Analysis results with pricing comparisons
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class BoQJobStatus(str, Enum):
    """Processing states for BoQ analysis jobs."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class BoQFileFormat(str, Enum):
    """Supported file formats for BoQ upload."""

    PDF = "pdf"
    XLSX = "xlsx"
    XLS = "xls"


class BoQItemType(str, Enum):
    """Classification of BoQ line items."""

    MATERIAL = "material"
    LABOR = "labor"
    EQUIPMENT = "equipment"
    UNKNOWN = "unknown"


# =============================================================================
# Request Schemas
# =============================================================================


class BoQUploadResponse(BaseModel):
    """Response after uploading a BoQ file."""

    job_id: str = Field(..., description="Unique job ID for tracking")
    status: BoQJobStatus = Field(default=BoQJobStatus.PENDING)
    message: str = Field(default="BoQ upload received. Processing will begin shortly.")
    ok: bool = Field(default=True)


# =============================================================================
# Item Schemas
# =============================================================================


class BoQItemBase(BaseModel):
    """Base fields for a BoQ line item."""

    section: Optional[str] = Field(None, description="Work section (e.g., 'PEKERJAAN KERAMIK')")
    item_number: Optional[str] = Field(None, description="Item number from BoQ")
    description: str = Field(..., description="Original description from BoQ")
    unit: Optional[str] = Field(None, description="Unit of measurement (m2, m1, unit, ls)")
    quantity: Optional[Decimal] = Field(None, description="Quantity from BoQ")
    contractor_unit_price: Optional[Decimal] = Field(None, description="Contractor's unit price (IDR)")
    contractor_total: Optional[Decimal] = Field(None, description="Contractor's total (IDR)")


class BoQItemExtracted(BoQItemBase):
    """Extracted item with classification."""

    item_type: BoQItemType = Field(default=BoQItemType.UNKNOWN)
    is_owner_supply: bool = Field(default=False, description="'Supply By Owner' item")
    is_existing: bool = Field(default=False, description="'use existing' item")
    extraction_confidence: Optional[float] = Field(
        None, ge=0, le=1, description="Extraction confidence (0-1)"
    )


class BoQItemPriced(BoQItemExtracted):
    """Item with Tokopedia price matching."""

    id: str = Field(..., description="Item UUID")

    # Tokopedia match
    search_query: Optional[str] = Field(None, description="Normalized search term used")
    tokopedia_product_name: Optional[str] = Field(None, description="Matched product name")
    tokopedia_price: Optional[Decimal] = Field(None, description="Tokopedia price per unit")
    tokopedia_url: Optional[str] = Field(None, description="Product URL")
    tokopedia_seller: Optional[str] = Field(None, description="Seller name")
    tokopedia_seller_location: Optional[str] = Field(None, description="Seller location")
    tokopedia_rating: Optional[float] = Field(None, description="Product rating (0-5)")
    tokopedia_sold_count: Optional[int] = Field(None, description="Units sold")
    match_confidence: Optional[float] = Field(
        None, ge=0, le=1, description="Match confidence (0-1)"
    )

    # Calculated fields
    market_unit_price: Optional[Decimal] = Field(None, description="Market unit price")
    market_total: Optional[Decimal] = Field(None, description="Market total")
    price_difference: Optional[Decimal] = Field(
        None, description="Contractor - Market price difference"
    )
    price_difference_percent: Optional[float] = Field(
        None, description="Price difference as percentage"
    )

    class Config:
        from_attributes = True


# =============================================================================
# Job Status Schemas
# =============================================================================


class BoQJobStatusResponse(BaseModel):
    """Response for job status check."""

    job_id: str
    status: BoQJobStatus
    progress_percent: int = Field(default=0, ge=0, le=100)
    message: Optional[str] = None
    error_message: Optional[str] = None

    # Counts (available during/after processing)
    total_items_extracted: int = Field(default=0)
    materials_count: int = Field(default=0)
    labor_count: int = Field(default=0)
    owner_supply_count: int = Field(default=0)

    created_at: datetime
    completed_at: Optional[datetime] = None


# =============================================================================
# Results Schemas
# =============================================================================


class BoQSummary(BaseModel):
    """High-level summary of BoQ analysis."""

    contractor_total: Decimal = Field(..., description="Total from contractor's BoQ")
    market_estimate: Decimal = Field(..., description="Estimated market total for materials")
    potential_savings: Decimal = Field(..., description="Potential savings (contractor - market)")
    savings_percent: float = Field(..., description="Savings as percentage")

    total_items: int = Field(..., description="Total items extracted")
    materials_count: int = Field(..., description="Items classified as materials")
    labor_count: int = Field(..., description="Items classified as labor")
    owner_supply_count: int = Field(..., description="Items marked 'Supply By Owner'")
    priced_count: int = Field(..., description="Materials with Tokopedia prices")


class BoQMetadata(BaseModel):
    """Metadata extracted from BoQ header."""

    project_name: Optional[str] = None
    contractor_name: Optional[str] = None
    project_location: Optional[str] = None
    filename: str


class BoQAnalysisResults(BaseModel):
    """Complete analysis results for a BoQ."""

    job_id: str
    status: BoQJobStatus
    metadata: BoQMetadata
    summary: BoQSummary

    # Categorized items
    owner_supply_items: list[BoQItemPriced] = Field(
        default_factory=list, description="Items you need to buy yourself"
    )
    overpriced_items: list[BoQItemPriced] = Field(
        default_factory=list, description="Items potentially overcharged (>10% above market)"
    )
    all_materials: list[BoQItemPriced] = Field(
        default_factory=list, description="All material items with pricing"
    )
    labor_items: list[BoQItemExtracted] = Field(
        default_factory=list, description="Labor items (not priced)"
    )

    completed_at: Optional[datetime] = None


# =============================================================================
# Internal Processing Schemas
# =============================================================================


class ExtractedBoQData(BaseModel):
    """Raw extraction result from GPT-4o Vision or Excel parser."""

    project_name: Optional[str] = None
    contractor_name: Optional[str] = None
    project_location: Optional[str] = None
    items: list[BoQItemExtracted] = Field(default_factory=list)
    extraction_warnings: list[str] = Field(default_factory=list)
