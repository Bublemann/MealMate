"""Reference data: categories, units, cuisines, tags (REF-01..04)."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

from app.domain.catalog import CUISINE_NAME_MAX_LENGTH, check_name
from app.domain.units import Unit, UnitKind


class Category(BaseModel):
    """Shown as the translation `category.<key>`, in `sort_order` (the shop's walking order)."""

    id: str
    key: str
    sort_order: int


class UnitInfo(BaseModel):
    """A unit (translation `unit.<unit>`) and its kind."""

    unit: Unit
    kind: UnitKind


class Cuisine(BaseModel):
    """Seeded cuisines have a `key` (translation `cuisine.<key>`), user-added ones a `name`."""

    id: str
    key: str | None
    name: str | None


class CuisineCreate(BaseModel):
    name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=CUISINE_NAME_MAX_LENGTH),
        AfterValidator(check_name),
    ]


class Tag(BaseModel):
    id: str
    name: str


class CategoryOrder(BaseModel):
    """Every category id exactly once, in the new order."""

    category_ids: Annotated[
        list[Annotated[str, StringConstraints(max_length=36)]], Field(max_length=100)
    ]
