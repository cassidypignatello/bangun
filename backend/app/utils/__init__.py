"""
Utility modules for backend services.
"""

from app.utils.cache import TTLCache, cached, material_search_cache, price_scrape_cache
from app.utils.resilience import (
    CircuitBreaker,
    CircuitBreakerError,
    with_circuit_breaker,
    with_retry,
    with_timeout,
)
from app.utils.text import normalize_material_name

__all__ = [
    "normalize_material_name",
    "CircuitBreaker",
    "CircuitBreakerError",
    "with_circuit_breaker",
    "with_retry",
    "with_timeout",
    "TTLCache",
    "cached",
    "material_search_cache",
    "price_scrape_cache",
]
