"""
Tests for application configuration settings
"""

import pytest

from app.config import Settings


# Required fields that must be provided for every Settings instantiation
REQUIRED_SETTINGS = {
    "supabase_url": "https://test.supabase.co",
    "supabase_service_key": "test_key",
    "openai_api_key": "sk-test",
    "apify_token": "apify_test",
    "midtrans_server_key": "SB-test",
    "midtrans_client_key": "SB-test-client",
    "field_encryption_key": "test_encryption_key",
}


class TestBoqPricingSettings:
    """Tests for BOQ pricing configuration settings"""

    def test_boq_max_price_lookups_default(self):
        """boq_max_price_lookups defaults to 20"""
        settings = Settings(**REQUIRED_SETTINGS)
        assert settings.boq_max_price_lookups == 20

    def test_marketplace_provider_default(self):
        """marketplace_provider defaults to 'tokopedia'"""
        settings = Settings(**REQUIRED_SETTINGS)
        assert settings.marketplace_provider == "tokopedia"

    def test_boq_max_price_lookups_override(self, monkeypatch):
        """boq_max_price_lookups can be overridden via environment variable"""
        monkeypatch.setenv("BOQ_MAX_PRICE_LOOKUPS", "50")
        settings = Settings(**REQUIRED_SETTINGS)
        assert settings.boq_max_price_lookups == 50

    def test_marketplace_provider_override(self, monkeypatch):
        """marketplace_provider can be overridden via environment variable"""
        monkeypatch.setenv("MARKETPLACE_PROVIDER", "shopee")
        settings = Settings(**REQUIRED_SETTINGS)
        assert settings.marketplace_provider == "shopee"

    def test_boq_max_price_lookups_explicit(self):
        """boq_max_price_lookups can be set explicitly via constructor"""
        settings = Settings(**REQUIRED_SETTINGS, boq_max_price_lookups=5)
        assert settings.boq_max_price_lookups == 5

    def test_marketplace_provider_explicit(self):
        """marketplace_provider can be set explicitly via constructor"""
        settings = Settings(**REQUIRED_SETTINGS, marketplace_provider="shopee")
        assert settings.marketplace_provider == "shopee"
