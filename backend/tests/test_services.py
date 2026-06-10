"""
Tests for business logic services
"""

import pytest
from unittest.mock import patch, AsyncMock


class TestSemanticMatcher:
    """Tests for semantic matching service"""

    def test_calculate_similarity_exact_match(self):
        """Should return 1.0 for identical strings"""
        from app.services.semantic_matcher import calculate_similarity

        result = calculate_similarity("Semen Portland", "Semen Portland")

        assert result == 1.0

    def test_calculate_similarity_case_insensitive(self):
        """Should be case insensitive"""
        from app.services.semantic_matcher import calculate_similarity

        result = calculate_similarity("SEMEN PORTLAND", "semen portland")

        assert result == 1.0

    def test_calculate_similarity_partial_match(self):
        """Should return partial score for similar strings"""
        from app.services.semantic_matcher import calculate_similarity

        result = calculate_similarity("Semen Portland 50kg", "Semen Portland")

        assert 0.7 < result < 1.0

    def test_calculate_similarity_no_match(self):
        """Should return low score for different strings"""
        from app.services.semantic_matcher import calculate_similarity

        result = calculate_similarity("Semen", "Keramik")

        assert result < 0.5

    @pytest.mark.asyncio
    async def test_find_exact_match_found(self):
        """Should return match when similarity > 0.95"""
        with patch("app.services.semantic_matcher.search_materials") as mock_history:
            # Use actual database schema fields: name_id, name_en, price_avg
            mock_history.return_value = [
                {"name_id": "Semen Portland 50kg", "name_en": "Portland Cement 50kg", "price_avg": 65000}
            ]

            from app.services.semantic_matcher import find_exact_match

            result = await find_exact_match("Semen Portland 50kg")

            assert result is not None
            assert result["source"] == "historical"
            assert result["confidence"] > 0.95

    @pytest.mark.asyncio
    async def test_find_exact_match_not_found(self):
        """Should return None when no exact match"""
        with patch("app.services.semantic_matcher.search_materials") as mock_history:
            mock_history.return_value = []

            from app.services.semantic_matcher import find_exact_match

            result = await find_exact_match("Unknown Material")

            assert result is None

    @pytest.mark.asyncio
    async def test_find_fuzzy_match_found(self):
        """Should return best fuzzy match above threshold"""
        with patch("app.services.semantic_matcher.search_materials") as mock_history:
            # Use actual database schema fields: name_id, name_en, price_avg
            mock_history.return_value = [
                {"name_id": "Semen Portland Tiga Roda", "name_en": "Portland Cement Tiga Roda", "price_avg": 65000},
                {"name_id": "Semen Holcim", "name_en": "Holcim Cement", "price_avg": 60000},
            ]

            from app.services.semantic_matcher import find_fuzzy_match

            result = await find_fuzzy_match("Semen Portland", threshold=0.5)

            assert result is not None
            assert result["source"] == "historical_fuzzy"

    @pytest.mark.asyncio
    async def test_find_fuzzy_match_below_threshold(self):
        """Should return None when no match above threshold"""
        with patch("app.services.semantic_matcher.search_materials") as mock_history:
            # Use actual database schema fields: name_id, name_en, price_avg
            mock_history.return_value = [
                {"name_id": "Keramik 60x60", "name_en": "Ceramic Tiles 60x60", "price_avg": 85000}
            ]

            from app.services.semantic_matcher import find_fuzzy_match

            result = await find_fuzzy_match("Semen Portland", threshold=0.9)

            assert result is None

    @pytest.mark.asyncio
    async def test_match_material_exact_first(self):
        """Should try exact match first"""
        with patch("app.services.semantic_matcher.find_exact_match") as mock_exact:
            mock_exact.return_value = {"source": "historical", "confidence": 0.98}

            from app.services.semantic_matcher import match_material

            result = await match_material("Semen Portland")

            assert result["source"] == "historical"
            mock_exact.assert_called_once()

    @pytest.mark.asyncio
    async def test_match_material_fallback_fuzzy(self):
        """Should fallback to fuzzy when no exact match"""
        with patch("app.services.semantic_matcher.find_exact_match") as mock_exact:
            with patch("app.services.semantic_matcher.find_fuzzy_match") as mock_fuzzy:
                mock_exact.return_value = None
                mock_fuzzy.return_value = {"source": "historical_fuzzy", "confidence": 0.8}

                from app.services.semantic_matcher import match_material

                result = await match_material("Semen Portland")

                assert result["source"] == "historical_fuzzy"


class TestTrustCalculator:
    """Tests for trust score calculation service (source-based 100-point algorithm)"""

    def test_calculate_trust_score_returns_detailed_object(self):
        """Should return TrustScoreDetailed with total_score and breakdown"""
        from app.services.trust_calculator import calculate_trust_score, SourceTier

        result = calculate_trust_score(
            source=SourceTier.GOOGLE_MAPS,
            review_count=125,
            rating=4.8,
        )

        assert hasattr(result, "total_score")
        assert hasattr(result, "trust_level")
        assert hasattr(result, "breakdown")
        assert result.total_score > 0

    def test_calculate_trust_score_minimum(self):
        """OLX source with no reviews/rating should score low"""
        from app.services.trust_calculator import calculate_trust_score, SourceTier

        result = calculate_trust_score(source=SourceTier.OLX)

        # OLX base = 9, no reviews/rating/verification/freshness = 9 total
        assert result.total_score == 9

    def test_calculate_trust_score_source_weights(self):
        """Manual/platform source should score higher than OLX"""
        from app.services.trust_calculator import calculate_trust_score, SourceTier

        olx_result = calculate_trust_score(source=SourceTier.OLX)
        gmaps_result = calculate_trust_score(source=SourceTier.GOOGLE_MAPS)
        manual_result = calculate_trust_score(source=SourceTier.MANUAL_CURATED)

        assert olx_result.total_score < gmaps_result.total_score
        assert gmaps_result.total_score <= manual_result.total_score

    def test_calculate_trust_score_reviews_add_points(self):
        """More reviews should add more points"""
        from app.services.trust_calculator import calculate_trust_score, SourceTier

        no_reviews = calculate_trust_score(source=SourceTier.GOOGLE_MAPS, review_count=0)
        many_reviews = calculate_trust_score(source=SourceTier.GOOGLE_MAPS, review_count=100)

        assert many_reviews.total_score > no_reviews.total_score

    def test_calculate_trust_score_high_rating_adds_points(self):
        """High rating should add points over no rating"""
        from app.services.trust_calculator import calculate_trust_score, SourceTier

        no_rating = calculate_trust_score(source=SourceTier.GOOGLE_MAPS)
        high_rating = calculate_trust_score(source=SourceTier.GOOGLE_MAPS, rating=4.8)

        assert high_rating.total_score > no_rating.total_score
        assert high_rating.breakdown["rating"] == 20

    def test_calculate_trust_score_verification_signals(self):
        """Photos, website, whatsapp, platform jobs each add points"""
        from app.services.trust_calculator import calculate_trust_score, SourceTier

        base = calculate_trust_score(source=SourceTier.GOOGLE_MAPS)
        verified = calculate_trust_score(
            source=SourceTier.GOOGLE_MAPS,
            photos_count=5,
            has_website=True,
            has_whatsapp=True,
            platform_jobs=3,
        )

        assert verified.total_score > base.total_score
        # photos(5) + website(3) + whatsapp(3) + platform(4) = 15
        assert verified.breakdown["verification"] == 15

    def test_create_trust_score_from_worker_dict(self):
        """Should create TrustScoreDetailed from a worker dict"""
        from app.services.trust_calculator import create_trust_score_from_worker_dict

        worker_data = {
            "source_tier": "google_maps",
            "gmaps_review_count": 50,
            "gmaps_rating": 4.5,
            "gmaps_photos_count": 10,
            "website": "https://example.com",
            "whatsapp": "+62812345678",
        }

        result = create_trust_score_from_worker_dict(worker_data)

        assert hasattr(result, "total_score")
        assert hasattr(result, "trust_level")
        assert result.total_score > 0

    def test_mask_worker_name_single_name(self):
        """Should mask single name showing first char"""
        from app.services.trust_calculator import mask_worker_name

        result = mask_worker_name("Wayan")

        assert result.startswith("W")
        assert len(result) > 1

    def test_mask_worker_name_two_names(self):
        """Should mask both name parts"""
        from app.services.trust_calculator import mask_worker_name

        result = mask_worker_name("Ahmad Suryanto")

        # Both parts masked, first char of each preserved
        assert result.startswith("A")
        assert "S" in result

    def test_mask_worker_name_multiple_names(self):
        """Should mask all name parts"""
        from app.services.trust_calculator import mask_worker_name

        result = mask_worker_name("Made Putra Wijaya")

        assert result.startswith("M")
        assert " " in result  # Multi-part name preserves spaces

    def test_mask_worker_name_with_whitespace(self):
        """Should handle extra whitespace"""
        from app.services.trust_calculator import mask_worker_name

        result = mask_worker_name("  John Doe  ")

        assert result.startswith("J")
        assert len(result) > 0
