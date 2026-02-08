"""Pydantic-based schema for MicroAPI service definitions."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Schema(BaseModel):
    """Base schema class for all MicroAPI request / response models.

    All schemas should inherit from this class.  Supports
    ``from_attributes=True`` for ORM-style model creation.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )
