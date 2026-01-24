"""
Bill of Materials (BOM) generation service using GPT-4o-mini
"""

import uuid
from datetime import datetime

from app.config import get_settings
from app.integrations.openai_client import generate_bom
from app.integrations.supabase import save_project, update_project_status
from app.schemas.estimate import BOMItem, EstimateResponse, EstimateStatus
from app.schemas.project import ProjectInput
from app.services.price_engine import enrich_bom_with_prices
from app.utils.affiliate import generate_affiliate_url


async def create_estimate(project: ProjectInput) -> EstimateResponse:
    """
    Create initial estimate record and trigger BOM generation

    Args:
        project: Project input with description and details

    Returns:
        EstimateResponse: Initial estimate with pending status
    """
    project_id = str(uuid.uuid4())
    now = datetime.utcnow()

    # Map to database schema (projects table)
    # project_type defaults to "general" if not provided (inferred from description by GPT)
    project_type_value = project.project_type.value if project.project_type else "general"

    project_data = {
        "id": project_id,
        "status": "draft",  # project_status enum value
        "project_type": project_type_value,
        "description": project.description,
        "location": project.location,
        "bom": [],  # JSONB column for BOM items
        "material_total": 0,
        "labor_total": 0,
        "total_estimate": 0,
    }

    # Save to database
    await save_project(project_data)

    return EstimateResponse(
        estimate_id=project_id,
        status=EstimateStatus.PENDING,
        project_type=project_type_value,
        bom_items=[],
        total_cost_idr=0,
        labor_cost_idr=0,
        grand_total_idr=0,
        created_at=now,
        updated_at=now,
    )


async def process_estimate(estimate_id: str, project: ProjectInput) -> None:
    """
    Background task to generate BOM and calculate prices

    Args:
        estimate_id: Estimate to process (project ID)
        project: Project input data

    Raises:
        Exception: If processing fails
    """
    settings = get_settings()

    try:
        # Update progress (keep status as "draft" since "processing" isn't in DB enum)
        # Frontend reads progress from price_range JSONB field
        await update_project_status(
            estimate_id,
            "draft",
            price_range={"step": "generating_bom", "progress": 10, "status": "processing"},
        )

        # Step 1: Generate BOM using GPT-4o-mini
        # Only description is required - project_type is optional
        project_dict = {
            "description": project.description,
        }

        if project.images:
            project_dict["images"] = [str(url) for url in project.images]

        raw_bom = await generate_bom(project_dict)

        # Update progress after BOM generation
        bom_count = len(raw_bom)
        await update_project_status(
            estimate_id,
            "draft",
            price_range={
                "step": "fetching_prices",
                "progress": 30,
                "bom_count": bom_count,
                "status": "processing",
                "current_item": 0,
                "current_material": "",
            },
        )

        # Step 2: Enrich with real-time prices (or mock data in dev mode)
        # Progress callback to update UI during slow Apify scraping
        async def on_price_progress(current: int, total: int, material_name: str, source: str):
            # Map 0..total to 30..80 progress range
            item_progress = 30 + int((current / total) * 50) if total > 0 else 30
            await update_project_status(
                estimate_id,
                "draft",
                price_range={
                    "step": "fetching_prices",
                    "progress": item_progress,
                    "bom_count": total,
                    "status": "processing",
                    "current_item": current,
                    "current_material": material_name[:50],  # Truncate for display
                    "current_source": source,  # cached, tokopedia, estimated, searching
                },
            )

        if settings.debug and settings.use_mock_prices:
            # Use mock prices in development to avoid Apify costs
            enriched_bom = await _mock_enrich_bom(raw_bom)
        else:
            enriched_bom = await enrich_bom_with_prices(raw_bom, on_progress=on_price_progress)

        # Update progress after price enrichment
        await update_project_status(
            estimate_id,
            "draft",
            price_range={"step": "calculating_totals", "progress": 80, "status": "processing"},
        )

        # Step 3: Calculate totals
        bom_items = []
        total_cost = 0

        for item in enriched_bom:
            marketplace_url = item.get("marketplace_url")
            bom_item = BOMItem(
                material_name=item["material_name"],
                english_name=item.get("english_name"),
                quantity=item["quantity"],
                unit=item["unit"],
                unit_price_idr=item["unit_price_idr"],
                total_price_idr=item["total_price_idr"],
                source=item["source"],
                confidence=item["confidence"],
                marketplace_url=marketplace_url,
                affiliate_url=generate_affiliate_url(marketplace_url),
            )
            bom_items.append(bom_item)
            total_cost += item["total_price_idr"]

        # Step 4: Calculate labor costs (simple heuristic: 30% of material cost)
        labor_cost = int(total_cost * 0.3)
        grand_total = total_cost + labor_cost

        # Step 5: Update database with completed estimate
        # Map to database schema
        await update_project_status(
            estimate_id,
            "estimated",  # project_status enum value for completed estimates
            bom=[item.model_dump() for item in bom_items],  # JSONB column
            material_total=total_cost,
            labor_total=labor_cost,
            total_estimate=grand_total,
            price_range={"step": "completed", "progress": 100},
        )

    except Exception as e:
        # Store error in price_range JSONB field for now
        await update_project_status(
            estimate_id,
            "draft",
            price_range={"error": str(e), "status": "failed"},
        )
        raise


async def _mock_enrich_bom(bom_items: list[dict]) -> list[dict]:
    """
    Mock price enrichment for development/testing without Apify costs.

    Uses realistic price estimates based on material category.
    Generates sample Tokopedia search URLs for testing the shopping list UI.
    """
    import random
    from urllib.parse import quote

    category_prices = {
        "structural": {"base": 150000, "variance": 50000},
        "finishing": {"base": 100000, "variance": 30000},
        "electrical": {"base": 75000, "variance": 25000},
        "plumbing": {"base": 120000, "variance": 40000},
        "hvac": {"base": 500000, "variance": 200000},
        "landscaping": {"base": 80000, "variance": 30000},
        "fixtures": {"base": 200000, "variance": 100000},
        "miscellaneous": {"base": 50000, "variance": 20000},
    }

    enriched = []
    for item in bom_items:
        category = item.get("category", "miscellaneous").lower()
        prices = category_prices.get(category, category_prices["miscellaneous"])

        unit_price = prices["base"] + random.randint(-prices["variance"], prices["variance"])
        quantity = item.get("quantity", 1)
        total_price = int(unit_price * quantity)

        # Generate mock Tokopedia search URL for testing the shopping list UI
        search_term = quote(item["material_name"])
        mock_url = f"https://www.tokopedia.com/search?q={search_term}"

        enriched.append({
            "material_name": item["material_name"],
            "english_name": item.get("english_name"),  # Pass through from OpenAI
            "quantity": quantity,
            "unit": item.get("unit", "pcs"),
            "unit_price_idr": unit_price,
            "total_price_idr": total_price,
            "source": "mock_data",
            "confidence": 0.5,
            "marketplace_url": mock_url,
        })

    return enriched
