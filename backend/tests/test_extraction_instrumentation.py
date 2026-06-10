"""
Tests for OpenAI token-usage instrumentation in BoQ extraction.
"""

from types import SimpleNamespace

from app.services.boq_processor import _log_openai_usage


class TestLogOpenaiUsage:
    def test_extracts_usage_fields(self):
        """Returns a dict of the three token counts from response.usage."""
        response = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=1200, completion_tokens=300, total_tokens=1500)
        )
        usage = _log_openai_usage(response, stage="test_stage", batch=1)
        assert usage == {"prompt_tokens": 1200, "completion_tokens": 300, "total_tokens": 1500}

    def test_returns_none_when_usage_missing(self):
        """Responses without usage (None) are tolerated."""
        assert _log_openai_usage(SimpleNamespace(usage=None), stage="test_stage") is None

    def test_handles_partial_usage(self):
        """Missing individual fields default to 0 rather than raising."""
        response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=100))
        usage = _log_openai_usage(response, stage="test_stage")
        assert usage["prompt_tokens"] == 100
        assert usage["completion_tokens"] == 0
        assert usage["total_tokens"] == 0

    def test_never_raises_on_context_collision(self):
        """A colliding context key must not raise (helper runs in the extraction hot path)."""
        response = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3)
        )
        usage = _log_openai_usage(response, stage="test_stage", total_tokens=999)
        assert usage == {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}


class TestModelKwargs:
    """Model-specific completion kwargs for the extraction call sites."""

    def test_legacy_models_use_max_tokens_and_temperature(self):
        from app.services.boq_processor import _model_kwargs

        kwargs = _model_kwargs("gpt-4o", 8000)
        assert kwargs == {"max_tokens": 8000, "temperature": 0.1}

    def test_gpt5_models_use_max_completion_tokens(self):
        from app.services.boq_processor import _model_kwargs

        kwargs = _model_kwargs("gpt-5.4-nano", 8000)
        assert kwargs == {"max_completion_tokens": 8000}
        assert "temperature" not in kwargs

    def test_gpt5_base_prefix_matches(self):
        from app.services.boq_processor import _model_kwargs

        assert "max_completion_tokens" in _model_kwargs("gpt-5.4", 4000)


class TestBatchTruncationDetection:
    def test_detects_length_finish_reason(self):
        from app.services.boq_processor import _is_truncated

        choice = SimpleNamespace(finish_reason="length")
        assert _is_truncated(choice) is True

    def test_normal_stop_is_not_truncated(self):
        from app.services.boq_processor import _is_truncated

        assert _is_truncated(SimpleNamespace(finish_reason="stop")) is False
        assert _is_truncated(SimpleNamespace(finish_reason=None)) is False


def _page_response(items, finish_reason="stop"):
    """Canned OpenAI-shaped response whose content is a JSON items payload."""
    import json as _json

    return SimpleNamespace(
        usage=None,
        choices=[SimpleNamespace(
            finish_reason=finish_reason,
            message=SimpleNamespace(refusal=None, content=_json.dumps({"items": items})),
        )],
    )


class TestExtractPagesIndividuallySync:
    def test_collects_items_across_pages(self):
        from unittest.mock import MagicMock
        from app.services.boq_processor import _extract_pages_individually_sync

        client = MagicMock()
        client.chat.completions.create.side_effect = [
            _page_response([{"description": "A"}]),
            _page_response([{"description": "B"}, {"description": "C"}]),
        ]

        items, warnings = _extract_pages_individually_sync(
            client, [{"type": "image_url"}, {"type": "image_url"}], "prompt", "gpt-4o"
        )

        assert [i.description for i in items] == ["A", "B", "C"]
        assert warnings == []

    def test_page_failure_recorded_not_raised(self):
        from unittest.mock import MagicMock
        from app.services.boq_processor import _extract_pages_individually_sync

        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("API down")

        items, warnings = _extract_pages_individually_sync(
            client, [{"type": "image_url"}], "prompt", "gpt-4o"
        )

        assert items == []
        assert len(warnings) == 1
        assert "failed" in warnings[0]

    def test_fallback_items_validate_into_extracted_data(self):
        """Recovered items must construct ExtractedBoQData without ValidationError."""
        from unittest.mock import MagicMock
        from app.schemas.boq import ExtractedBoQData
        from app.services.boq_processor import _extract_pages_individually_sync

        # Raw-dict field names mirror what the batch loop reads from GPT output:
        # contractor_unit_price / contractor_total, passed straight to Pydantic.
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            _page_response([
                {"description": "Pek. Plester dinding", "item_type": "work",
                 "quantity": 10, "unit": "m2",
                 "contractor_unit_price": 50000, "contractor_total": 500000},
                {"item_type": "materials"},  # missing description, variant type
            ]),
        ]

        items, warnings = _extract_pages_individually_sync(
            client, [{"type": "image_url"}], "p", "gpt-4o"
        )

        data = ExtractedBoQData(items=items)  # must not raise
        assert len(data.items) == 2
        assert data.items[0].item_type.value == "labor"  # "work" normalized
        assert data.items[1].item_type.value == "material"  # "materials" normalized
        assert data.items[1].description == ""

    def test_page_offset_threads_into_warnings(self):
        """Page numbers in warnings are absolute, not intra-batch indices."""
        from unittest.mock import MagicMock
        from app.services.boq_processor import _extract_pages_individually_sync

        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("boom")

        items, warnings = _extract_pages_individually_sync(
            client, [{"type": "image_url"}], "prompt", "gpt-4o", page_offset=6
        )

        assert items == []
        assert "page 6" in warnings[0]


class TestTruncatedBatchRecovery:
    def test_truncated_batch_with_valid_json_goes_to_fallback(self, monkeypatch):
        """finish_reason=='length' must trigger page-by-page recovery even when
        the truncated content parses as valid (but incomplete) JSON."""
        import fitz
        from unittest.mock import MagicMock
        import app.config
        from app.services import boq_processor

        doc = fitz.open()
        doc.new_page()
        doc.new_page()  # page 0 is skipped as cover; one page is processed
        pdf_bytes = doc.tobytes()
        doc.close()

        settings = SimpleNamespace(
            boq_dry_run=False,
            openai_api_key="sk-test",
            boq_max_pages=10,
            boq_extraction_model="gpt-4o",
        )
        monkeypatch.setattr(app.config, "get_settings", lambda: settings)

        client = MagicMock()
        client.chat.completions.create.side_effect = [
            # Batch call: valid JSON but cut off by the output-token cap.
            _page_response([{"description": "INCOMPLETE"}], finish_reason="length"),
            # Fallback per-page call recovers the real items.
            _page_response([{"description": "Recovered A"}, {"description": "Recovered B"}]),
        ]
        import openai
        monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: client)

        result = boq_processor._extract_from_pdf_sync(pdf_bytes, "test.pdf")

        assert [i.description for i in result.items] == ["Recovered A", "Recovered B"]
        assert any("hit the output limit" in w for w in result.extraction_warnings)
        assert client.chat.completions.create.call_count == 2
