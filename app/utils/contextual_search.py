"""Composable SQLAlchemy predicates for contextual text search."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement

_MAX_QUERY_LENGTH = 200
_LIKE_ESCAPE = "\\"


def normalize_search_terms(query: str | None) -> list[str]:
    """Return bounded, whitespace-separated search terms."""
    normalized = (query or "").strip()[:_MAX_QUERY_LENGTH]
    return [term for term in normalized.split() if term]


def contextual_search(*columns: Any, query: str | None) -> ColumnElement[bool] | None:
    """Match each query term in any supplied column using bound LIKE values.

    Terms are ANDed, while columns are ORed per term. SQL wildcard characters
    from user input are escaped so they behave as literal search characters.
    """
    terms = normalize_search_terms(query)
    if not terms or not columns:
        return None

    groups = []
    for term in terms:
        escaped = term.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2).replace("%", _LIKE_ESCAPE + "%").replace("_", _LIKE_ESCAPE + "_")
        pattern = f"%{escaped}%"
        groups.append(or_(*(column.ilike(pattern, escape=_LIKE_ESCAPE) for column in columns)))
    return and_(*groups)
