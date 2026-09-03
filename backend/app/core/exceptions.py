"""Typed application exceptions and the global error handlers (rules.md 3;
techspec.md 5.3).

Each error maps to a stable ``code`` the global handler turns into the one error
envelope. Handlers are registered on the app in ``app.main``.
"""
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

REQUEST_ID_ATTR: str = "request_id"
_VALIDATION_STATUS: int = 422
_VALIDATION_CODE: str = "VALIDATION_ERROR"
_UNHANDLED_STATUS: int = 500
_UNHANDLED_CODE: str = "INTERNAL_ERROR"


class MargError(Exception):
    """Base class for all application errors."""

    code: str = "INTERNAL_ERROR"
    status_code: int = 500

    def __init__(
        self, message: str, details: Optional[dict] = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class CameraNotFoundError(MargError):
    """Raised when a camera referenced by an operation is absent from the graph.

    An absent camera is a configuration error (a broken topology), not a match
    outcome — surfacing it as an exception keeps it from being mistaken for a
    matching failure.
    """

    # code/status_code per techspec.md 5.3 (confirmed 2026-09-03).
    code = "CAMERA_NOT_FOUND"
    status_code = 404

    def __init__(self, camera_id: str) -> None:
        super().__init__(
            f"Camera not present in the camera graph: {camera_id}",
            details={"camera_id": camera_id},
        )
        self.camera_id = camera_id


class IngestKeyError(MargError):
    """Raised when the ingest key is missing or does not match."""

    code = "INVALID_INGEST_KEY"
    status_code = 401


class NotFoundError(MargError):
    """Raised when a requested resource does not exist."""

    code = "NOT_FOUND"
    status_code = 404


def _request_id(request: Request) -> Optional[str]:
    return getattr(request.state, REQUEST_ID_ATTR, None)


def _envelope(
    code: str, message: str, request_id: Optional[str], details: Optional[dict]
) -> dict:
    """Build the one error envelope shape (techspec.md 5.3)."""
    error: dict = {"code": code, "message": message, "request_id": request_id}
    if details is not None:
        error["details"] = details
    return {"error": error}


async def _marg_error_handler(request: Request, exc: MargError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(exc.code, exc.message, _request_id(request), exc.details),
    )


async def _validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=_VALIDATION_STATUS,
        content=_envelope(
            _VALIDATION_CODE,
            "Request validation failed.",
            _request_id(request),
            {"errors": exc.errors()},
        ),
    )


async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    # Never leak internals (rules.md 3): the message is generic, the request_id
    # is the bridge to the server log line that has the detail.
    return JSONResponse(
        status_code=_UNHANDLED_STATUS,
        content=_envelope(
            _UNHANDLED_CODE,
            "Something went wrong on the server.",
            _request_id(request),
            None,
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register the global handlers that emit the techspec.md 5.3 envelope."""
    app.add_exception_handler(MargError, _marg_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_handler)
