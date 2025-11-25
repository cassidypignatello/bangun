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
            mock_history.return_value = [
                {"material_name": "Semen Portland 50kg", "unit_price_idr": 65000}
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
            mock_history.return_value = [
                {"material_name": "Semen Portland Tiga Roda", "unit_price_idr": 65000},
                {"material_name": "Semen Holcim", "unit_price_idr": 60000},
            ]

            from app.services.semantic_matcher import find_fuzzy_match

            result = await find_fuzzy_match("Semen Portland", threshold=0.5)

            assert result is not None
            assert result["source"] == "historical_fuzzy"

    @pytest.mark.asyncio
    async def test_find_fuzzy_match_below_threshold(self):
        """Should return None when no match above threshold"""
        with patch("app.services.semantic_matcher.search_materials") as mock_history:
            mock_history.return_value = [
                {"material_name": "Keramik 60x60", "unit_price_idr": 85000}
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
    """Tests for trust score calculation service"""

    def test_calculate_trust_score_perfect(self):
        """Should return 1.0 for perfect worker"""
        from app.services.trust_calculator import calculate_trust_score

        result = calculate_trust_score(
            project_count=100,
            avg_rating=5.0,
            license_verified=True,
            insurance_verified=True,
            background_check=True,
            years_experience=30,
        )

        assert result == 1.0

    def test_calculate_trust_score_minimum(self):
        """Should return 0.0 for new worker with no credentials"""
        from app.services.trust_calculator import calculate_trust_score

        result = calculate_trust_score(
            project_count=0,
            avg_rating=0.0,
            license_verified=False,
            insurance_verified=False,
            background_check=False,
            years_experience=0,
        )

        assert result == 0.0

    def test_calculate_trust_score_weights(self):
        """Should apply correct weights to components"""
        from app.services.trust_calculator import calculate_trust_score

        # Only license verified (15%)
        license_only = calculate_trust_score(
            project_count=0,
            avg_rating=0.0,
            license_verified=True,
            insurance_verified=False,
            background_check=False,
            years_experience=0,
        )
        assert license_only == 0.15

        # Only insurance verified (15%)
        insurance_only = calculate_trust_score(
            project_count=0,
            avg_rating=0.0,
            license_verified=False,
            insurance_verified=True,
            background_check=False,
            years_experience=0,
        )
        assert insurance_only == 0.15

        # Only background check (10%)
        bg_only = calculate_trust_score(
            project_count=0,
            avg_rating=0.0,
            license_verified=False,
            insurance_verified=False,
            background_check=True,
            years_experience=0,
        )
        assert bg_only == 0.10

    def test_calculate_trust_score_normalized_projects(self):
        """Should cap project score at 50 projects"""
        from app.services.trust_calculator import calculate_trust_score

        score_50 = calculate_trust_score(50, 0.0, False, False, False, 0)
        score_100 = calculate_trust_score(100, 0.0, False, False, False, 0)

        # Both should give max 20% for projects
        assert score_50 == score_100 == 0.20

    def test_calculate_trust_score_normalized_experience(self):
        """Should cap experience score at 20 years"""
        from app.services.trust_calculator import calculate_trust_score

        score_20 = calculate_trust_score(0, 0.0, False, False, False, 20)
        score_40 = calculate_trust_score(0, 0.0, False, False, False, 40)

        # Both should give max 10% for experience
        assert score_20 == score_40 == 0.10

    def test_create_trust_score_returns_object(self):
        """Should return TrustScore object"""
        from app.services.trust_calculator import create_trust_score

        worker_data = {
            "project_count": 25,
            "avg_rating": 4.5,
            "license_verified": True,
            "insurance_verified": True,
            "background_check": False,
            "years_experience": 10,
        }

        result = create_trust_score(worker_data)

        assert hasattr(result, "overall_score")
        assert result.project_count == 25
        assert result.avg_rating == 4.5
        assert result.license_verified is True

    def test_mask_worker_name_single_name(self):
        """Should mask single name"""
        from app.services.trust_calculator import mask_worker_name

        result = mask_worker_name("Wayan")

        assert result == "W****"

    def test_mask_worker_name_two_names(self):
        """Should show first name, mask last"""
        from app.services.trust_calculator import mask_worker_name

        result = mask_worker_name("Ahmad Suryanto")

        assert result == "Ahmad S****"

    def test_mask_worker_name_multiple_names(self):
        """Should show first name, mask last only"""
        from app.services.trust_calculator import mask_worker_name

        result = mask_worker_name("Made Putra Wijaya")

        assert result == "Made W****"

    def test_mask_worker_name_with_whitespace(self):
        """Should handle extra whitespace"""
        from app.services.trust_calculator import mask_worker_name

        result = mask_worker_name("  John Doe  ")

        assert result == "John D****"
