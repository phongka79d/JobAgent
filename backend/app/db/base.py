"""Single declarative base and SQLAlchemy naming convention for application tables.

Constraint and index name templates follow Master Plan Section 6.1:
``pk_``, ``fk_``, ``uq_``, ``ck_``, and ``ix_`` prefixes with double-underscore
column/rule separators. Models may still set explicit names when multi-column
identifiers differ from the single-column template.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Master Section 6.1 naming conventions for unnamed constraints/indexes.
NAMING_CONVENTION: dict[str, str] = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s__%(column_0_name)s",
    "uq": "uq_%(table_name)s__%(column_0_name)s",
    "ck": "ck_%(table_name)s__%(constraint_name)s",
    "ix": "ix_%(table_name)s__%(column_0_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Application declarative base; one metadata owner for all ORM tables."""

    metadata = metadata
