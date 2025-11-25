"""
Rate limiting configuration using SlowAPI
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Create limiter instance
limiter = Limiter(key_func=get_remote_address)

# Rate limit decorators for common use cases
STANDARD_LIMIT = "60/minute"
HEAVY_LIMIT = "10/minute"
LIGHT_LIMIT = "100/minute"
