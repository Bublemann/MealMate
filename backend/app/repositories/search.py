"""Search on `*_norm` columns (ING-03, REF-04)."""

from sqlalchemy import ColumnElement, func, or_
from sqlalchemy.orm import InstrumentedAttribute

from app.domain.text import UMLAUT_SPELLINGS, fold_umlauts

type Column = ColumnElement[str] | InstrumentedAttribute[str]


def folded(column: Column) -> ColumnElement[str]:
    """The column with umlaut spellings folded in SQL, as `fold_umlauts` does."""
    expression: ColumnElement[str] = func.coalesce(column, "")
    for spelled, plain in UMLAUT_SPELLINGS:
        expression = func.replace(expression, spelled, plain)
    return expression


def contains(column: Column, query_norm: str) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    """The conditions "the normalised column contains the normalised query" and "it starts
    with it", each also true when they match with umlaut spellings folded."""
    position = func.instr(column, query_norm)
    folded_position = func.instr(folded(column), fold_umlauts(query_norm))
    return (
        or_(position > 0, folded_position > 0),
        or_(position == 1, folded_position == 1),
    )
