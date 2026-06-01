"""SQLAlchemy declarative base and portable column types."""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    type_annotation_map = {
        dict: JSON,
        list: JSON,
    }
