"""
Bill of Materials (BOM) generation service using GPT-4o-mini
"""

import uuid
from datetime import datetime

from app.integrations.openai_client import generate_bom
from app.integrations.supabase import save_project, update_project_status
from app.schemas.estimate import BOMItem, EstimateResponse, EstimateStatus
from app.schemas.project import ProjectInput
from app.services.price_engine import enrich_bom_with_prices


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
    project_data = {
        "id": project_id,
        "status": "draft",  # project_status enum value
        "project_type": project.project_type.value,
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
        project_type=project.project_type.value,
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
    try:
        # Step 1: Generate BOM using GPT-4o-mini
        project_dict = {
            "project_type": project.project_type.value,
            "description": project.description,
            "location": project.location,
        }

        raw_bom = await generate_bom(project_dict)

        # Step 2: Enrich with real-time prices
        enriched_bom = await enrich_bom_with_prices(raw_bom)

        # Step 3: Calculate totals
        bom_items = []
        total_cost = 0

        for item in enriched_bom:
            bom_item = BOMItem(
                material_name=item["material_name"],
                quantity=item["quantity"],
                unit=item["unit"],
                unit_price_idr=item["unit_price_idr"],
                total_price_idr=item["total_price_idr"],
                source=item["source"],
                confidence=item["confidence"],
                marketplace_url=item.get("marketplace_url"),
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
        )

    except Exception as e:
        # Store error in price_range JSONB field for now
        await update_project_status(
            estimate_id,
            "draft",
            price_range={"error": str(e), "status": "failed"},
        )
        raise
