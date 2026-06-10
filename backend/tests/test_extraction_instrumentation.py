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
