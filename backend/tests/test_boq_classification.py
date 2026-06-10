"""
Tests for BoQ item type classification overrides.
"""

from app.schemas.boq import BoQItemType
from app.services.boq_processor import _normalize_item_type


class TestStrongLaborOverrides:
    """Application charges must classify as labor even when GPT says material."""

    def test_paint_application_overrides_material(self):
        assert _normalize_item_type("material", "Cat dinding interior lantai 1") == BoQItemType.LABOR
        assert _normalize_item_type("material", "Cat plafond (ex vinilex)") == BoQItemType.LABOR

    def test_refinishing_overrides_material(self):
        assert _normalize_item_type("material", "Refinishing pintu kayu existing") == BoQItemType.LABOR

    def test_waterproofing_overrides_material(self):
        assert _normalize_item_type("material", "Waterproofing kolam renang") == BoQItemType.LABOR

    def test_named_products_stay_material(self):
        """A supplied product is still material — overrides must not over-trigger."""
        assert _normalize_item_type("material", "Granit Lantai 60x60") == BoQItemType.MATERIAL
        assert _normalize_item_type("material", "Pipa PVC Rucika 4 inch") == BoQItemType.MATERIAL

    def test_pas_prefix_items_keep_gpt_label(self):
        """Pas. (install) items are a known convention difference — do NOT override."""
        assert _normalize_item_type("material", "Pas. Granit Dinding (Suply By Owner)") == BoQItemType.MATERIAL
