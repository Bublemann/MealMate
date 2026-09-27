"""Ingredients: the shared wiki (ING-01..06), their nutrition (NUT-02), and the admin actions
merge and delete (ING-05).

Everyone views and edits ingredients (plan § 5.5, `services.access`); merging and deleting need
an admin, which the API checks. Name uniqueness and the base-unit guard are checked inside the
write transaction, which holds the write lock (`BEGIN IMMEDIATE`).

References from later milestones go through `services.hooks`: `ingredient_references` (M4 adds
`meal_ingredients`, M5a the list tables) blocks deletion, and `on_ingredients_merged` repoints
them when merging.
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ApiError,
    ErrorCode,
    FieldErrorCode,
    FieldProblem,
    not_found,
    validation_error,
)
from app.domain.nutrition import ingredient_nutrition
from app.domain.reference import OTHER_CATEGORY
from app.domain.similarity import similar_names
from app.domain.text import normalize
from app.models import Ingredient as IngredientRow
from app.repositories import ingredients as ingredients_repo
from app.repositories import products as products_repo
from app.repositories import reference as reference_repo
from app.schemas.admin import AdminAction
from app.schemas.ingredients import (
    Ingredient,
    IngredientCreate,
    IngredientSummary,
    IngredientUpdate,
)
from app.schemas.nutrition import IngredientNutrition, NutrientInfo, NutrientValues
from app.schemas.products import Product
from app.services import events, hooks, products
from app.services.principal import Principal
from app.services.products import base_unit_name
from app.services.users import user_refs

SEARCH_LIMIT = 1000


def _name_taken() -> FieldProblem:
    return FieldProblem(("body", "name"), FieldErrorCode.TAKEN)


def summary(row: IngredientRow, product_count: int) -> IngredientSummary:
    return IngredientSummary(
        id=row.id,
        name=row.name,
        category_id=row.category_id,
        base_unit=base_unit_name(row.base_unit),
        product_count=product_count,
    )


async def _ingredient(session: AsyncSession, row: IngredientRow) -> Ingredient:
    linked = await products_repo.for_ingredient(session, row.id)
    manual = row.nutrients()
    nutrition = ingredient_nutrition(manual, [item.nutrients() for item in linked])
    refs = await user_refs(session, [row.created_by, row.updated_by])
    return Ingredient(
        id=row.id,
        name=row.name,
        category_id=row.category_id,
        base_unit=base_unit_name(row.base_unit),
        piece_weight_g=row.piece_weight_g,
        density_g_per_ml=row.density_g_per_ml,
        manual=NutrientValues.model_validate(manual),
        nutrition=IngredientNutrition.model_validate(
            {
                key: NutrientInfo(
                    value=value.value,
                    source=value.source,
                    products_mean=value.products_mean,
                    products_count=value.products_count,
                )
                for key, value in nutrition.items()
            }
        ),
        product_count=len(linked),
        created_by=refs.get(row.created_by) if row.created_by else None,
        updated_by=refs.get(row.updated_by) if row.updated_by else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _category_problem(session: AsyncSession, category_id: str) -> FieldProblem | None:
    if await reference_repo.get_category(session, category_id) is None:
        return FieldProblem(("body", "category_id"), FieldErrorCode.INVALID)
    return None


async def _other_category_id(session: AsyncSession) -> str:
    other = await reference_repo.category_by_key(session, OTHER_CATEGORY)
    if other is None:  # pragma: no cover -- seeded by migration 0003, never deleted (REF-01)
        raise RuntimeError("the 'other' category is missing")
    return other.id


async def search(
    session: AsyncSession, *, query: str | None, category_id: str | None
) -> list[IngredientSummary]:
    """Search by name ignoring case, umlaut spelling and accents (ING-03): prefix matches
    first, then by name. Without a query: every ingredient (at most 1000) by category order
    and name."""
    async with session.begin():
        rows = await ingredients_repo.search(
            session, query=normalize(query or ""), category_id=category_id, limit=SEARCH_LIMIT
        )
    return [summary(row, count) for row, count in rows]


async def similar(session: AsyncSession, name: str) -> list[IngredientSummary]:
    """Up to five ingredients with a name similar to `name` (the hint of ING-03)."""
    async with session.begin():
        ids = similar_names(normalize(name), await ingredients_repo.names(session))
        rows = await ingredients_repo.with_product_counts(session, ids)
    return [summary(*rows[ingredient_id]) for ingredient_id in ids]


async def get_ingredient(session: AsyncSession, ingredient_id: str) -> Ingredient:
    async with session.begin():
        row = await ingredients_repo.get(session, ingredient_id)
        if row is None:
            raise not_found()
        return await _ingredient(session, row)


async def list_products(session: AsyncSession, ingredient_id: str) -> list[Product]:
    """The ingredient's products, by name and barcode."""
    async with session.begin():
        if await ingredients_repo.get(session, ingredient_id) is None:
            raise not_found()
        return await products.products(
            session, await products_repo.for_ingredient(session, ingredient_id)
        )


async def create_ingredient(
    session: AsyncSession, principal: Principal, body: IngredientCreate, *, now: datetime
) -> Ingredient:
    """Add an ingredient (ING-02); its name must be unique ignoring case and umlaut spelling."""
    name_norm = normalize(body.name)
    async with session.begin():
        problems: list[FieldProblem] = []
        if await ingredients_repo.name_taken(session, name_norm):
            problems.append(_name_taken())
        if body.category_id is not None and (
            problem := await _category_problem(session, body.category_id)
        ):
            problems.append(problem)
        if problems:
            raise validation_error(problems)
        row = IngredientRow(
            name=body.name,
            name_norm=name_norm,
            category_id=body.category_id or await _other_category_id(session),
            base_unit=body.base_unit,
            piece_weight_g=body.piece_weight_g,
            density_g_per_ml=body.density_g_per_ml,
            created_by=principal.user_id,
            updated_by=principal.user_id,
            created_at=now,
            updated_at=now,
        )
        row.set_nutrients((body.manual or NutrientValues()).model_dump())
        session.add(row)
        await session.flush()
        return await _ingredient(session, row)


async def update_ingredient(
    session: AsyncSession,
    principal: Principal,
    ingredient_id: str,
    body: IngredientUpdate,
    *,
    now: datetime,
) -> Ingredient:
    """Change the fields that were sent and record who changed it last (ING-01). The base
    unit only changes while no product is linked (ING-02)."""
    sent = body.model_fields_set
    async with session.begin():
        row = await ingredients_repo.get(session, ingredient_id)
        if row is None:
            raise not_found()
        problems: list[FieldProblem] = []
        name_norm = None if body.name is None else normalize(body.name)
        if name_norm is not None and await ingredients_repo.name_taken(
            session, name_norm, except_id=row.id
        ):
            problems.append(_name_taken())
        if body.category_id is not None and (
            problem := await _category_problem(session, body.category_id)
        ):
            problems.append(problem)
        if problems:
            raise validation_error(problems)
        if (
            body.base_unit is not None
            and body.base_unit != row.base_unit
            and await products_repo.count_for(session, row.id) > 0
        ):
            raise ApiError(ErrorCode.INGREDIENT_BASE_UNIT_LOCKED, status_code=409)

        if body.name is not None and name_norm is not None:
            row.name, row.name_norm = body.name, name_norm
        if body.category_id is not None:
            row.category_id = body.category_id
        if body.base_unit is not None:
            row.base_unit = body.base_unit
        if "piece_weight_g" in sent:
            row.piece_weight_g = body.piece_weight_g
        if "density_g_per_ml" in sent:
            row.density_g_per_ml = body.density_g_per_ml
        if body.manual is not None:
            row.set_nutrients(body.manual.model_dump(include=body.manual.model_fields_set))
        row.updated_by = principal.user_id
        row.updated_at = now
        await session.flush()
        return await _ingredient(session, row)


async def merge(
    session: AsyncSession, actor: Principal, ingredient_id: str, into_id: str, *, now: datetime
) -> Ingredient:
    """Merge a duplicate into another ingredient (ING-05, admins): every reference moves to
    `into_id`, then the duplicate is deleted. The target keeps its own attributes and values;
    it and the moved products record the admin as the one who changed them last.

    Moving products to an ingredient with another base unit would break their nutrition
    basis, so that is refused (409 `ingredient.merge_base_unit_mismatch`).
    """
    if into_id == ingredient_id:
        raise validation_error([FieldProblem(("body", "into_id"), FieldErrorCode.INVALID)])
    async with session.begin():
        source = await ingredients_repo.get(session, ingredient_id)
        if source is None:
            raise not_found()
        target = await ingredients_repo.get(session, into_id)
        if target is None:
            raise validation_error([FieldProblem(("body", "into_id"), FieldErrorCode.INVALID)])
        if (
            source.base_unit != target.base_unit
            and await products_repo.count_for(session, source.id) > 0
        ):
            raise ApiError(ErrorCode.INGREDIENT_MERGE_BASE_UNIT_MISMATCH, status_code=409)
        await products_repo.move(session, source.id, target.id, actor_id=actor.user_id, now=now)
        await hooks.on_ingredients_merged(session, source.id, target.id)
        target.updated_by = actor.user_id
        target.updated_at = now
        events.record(
            session,
            actor_id=actor.user_id,
            action=AdminAction.INGREDIENT_MERGE,
            target_user_id=None,
            now=now,
            details={"from_name": source.name, "into_name": target.name},
        )
        await session.delete(source)
        await session.flush()
        return await _ingredient(session, target)


async def delete(
    session: AsyncSession, actor: Principal, ingredient_id: str, *, now: datetime
) -> None:
    """Delete an ingredient nothing refers to (ING-05, admins); otherwise 409
    `ingredient.in_use` with the number of references per kind."""
    async with session.begin():
        row = await ingredients_repo.get(session, ingredient_id)
        if row is None:
            raise not_found()
        references = {
            "products": await products_repo.count_for(session, row.id),
            **await hooks.ingredient_references(session, row.id),
        }
        if any(references.values()):
            raise ApiError(ErrorCode.INGREDIENT_IN_USE, status_code=409, params=references)
        events.record(
            session,
            actor_id=actor.user_id,
            action=AdminAction.INGREDIENT_DELETE,
            target_user_id=None,
            now=now,
            details={"name": row.name},
        )
        await session.delete(row)
