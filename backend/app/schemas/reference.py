"""Reference data: categories, units, cuisines, tags (REF-01..04)."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

from app.domain.catalog import CATEGORY_NAME_MAX_LENGTH, CUISINE_NAME_MAX_LENGTH, check_name
from app.domain.units import Unit, UnitKind
from app.schemas.ingredients import BaseUnitName

CategoryName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=CATEGORY_NAME_MAX_LENGTH),
    AfterValidator(check_name),
]


class CategoryNames(BaseModel):
    """A category's name in each UI language (I18N-04, D-31). Both are required; each is unique
    in its language among the categories that aren't deleted, ignoring case, umlauts and accents
    (REF-01)."""

    de: CategoryName
    en: CategoryName


class Category(BaseModel):
    """Shown by its name in the UI language (`names`), in `sort_order` (the shop's walking
    order). `key` names a seeded category, e.g. `other` for *Other* and `uncategorized` for
    *Uncategorized*; the categories admins add have none.

    A `deleted` category (D-30) can no longer be picked or ordered, but lists being shopped and
    done lists still show it. It keeps its last `sort_order`, which the next category in the
    walking order took over: its lines come right after that one's.

    `ingredient_count`: how many ingredients it holds, so that the Ingredients tab offers
    *Uncategorized* in its filter only while it holds some (ING-03)."""

    id: str
    key: str | None
    names: CategoryNames
    sort_order: int
    deleted: bool
    ingredient_count: int


class CategoryCreate(BaseModel):
    """A new category; it goes last in the walking order (REF-01)."""

    names: CategoryNames


class CategoryRename(BaseModel):
    """New names for a category, replacing both (REF-01)."""

    names: CategoryNames


class CategoryUsage(BaseModel):
    """What deleting a category would move (ADM-01): its `ingredients` to *Uncategorized*, and
    the free-text extra items on drafts (`extra_items`) to *Other*."""

    ingredients: int
    extra_items: int


class UnitInfo(BaseModel):
    """A unit (translation `unit.<unit>`), its kind, and the base units of the ingredients it
    fits (REF-02): an amount of an ingredient takes only the units whose `base_units` hold the
    ingredient's base unit. An amount without a unit counts as pieces."""

    unit: Unit
    kind: UnitKind
    base_units: list[BaseUnitName]


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
    """Every category that isn't deleted exactly once, *Uncategorized* included, in the new
    order."""

    category_ids: Annotated[
        list[Annotated[str, StringConstraints(max_length=36)]], Field(max_length=100)
    ]
