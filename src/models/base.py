"""SQLAlchemy 2.0 declarative base and shared mixins."""

import datetime
from enum import Enum

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    """Extract enum .value strings for sa.Enum(values_callable=...).

    StrEnum names are UPPERCASE but values are lowercase.
    SQLAlchemy defaults to names; this forces values to match
    the PostgreSQL enum type created by Alembic migrations.
    """
    return [m.value for m in enum_cls]


class Base(DeclarativeBase):
    """Declarative base for all mailwise ORM models."""

    pass


class TimestampMixin:
    """Mixin that adds created_at and updated_at to any model.

    Both columns use server-side defaults (func.now()) so they are populated
    even when rows are inserted outside the ORM (e.g., alembic bulk_insert).
    updated_at is refreshed on every UPDATE via onupdate.
    """

    created_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
