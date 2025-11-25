"""
Standard error handling middleware for FastAPI
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


def error_response(code: str, message: str, status_code: int = 400) -> JSONResponse:
    """
    Standard error response format

    Args:
        code: Error code identifier
        message: Human-readable error message
        status_code: HTTP status code

    Returns:
        JSONResponse: Standardized error response
    """
    return JSONResponse(
        status_code=status_code,
        content={"error": code, "message": message, "ok": False},
    )


def add_error_handlers(app: FastAPI) -> None:
    """
    Register error handlers with FastAPI application

    Args:
        app: FastAPI application instance
    """

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        """Handle validation errors"""
        return error_response(
            code="VALIDATION_ERROR",
            message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    @app.exception_handler(KeyError)
    async def key_error_handler(request: Request, exc: KeyError):
        """Handle missing key errors"""
        return error_response(
            code="MISSING_FIELD",
            message=f"Missing required field: {exc}",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Catch-all error handler"""
        return error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
