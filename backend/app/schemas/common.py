"""Shared response schemas (techspec.md 5.2)."""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """The list envelope wrapping every collection response (techspec.md 5.2)."""

    items: list[T]
    total: int
    limit: int
    offset: int


class HealthRead(BaseModel):
    """Liveness payload for GET /system/health."""

    status: str
    index_size: int
    camera_count: int
