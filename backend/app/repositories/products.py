"""Queries on `products`."""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Product


async def get(session: AsyncSession, product_id: str) -> Product | None:
    return await session.get(Product, product_id)


async def barcode_taken(
    session: AsyncSession, barcode: str, *, except_id: str | None = None
) -> bool:
    query = select(Product.id).where(Product.barcode == barcode)
    if except_id is not None:
        query = query.where(Product.id != except_id)
    return (await session.execute(query)).first() is not None


async def for_ingredient(session: AsyncSession, ingredient_id: str) -> Sequence[Product]:
    result = await session.execute(select(Product).where(Product.ingredient_id == ingredient_id))
    return result.scalars().all()


async def count_for(session: AsyncSession, ingredient_id: str) -> int:
    result = await session.execute(
        select(func.count()).where(Product.ingredient_id == ingredient_id)
    )
    return result.scalar_one()


async def move(
    session: AsyncSession,
    from_ingredient_id: str,
    to_ingredient_id: str,
    *,
    actor_id: str,
    now: datetime,
) -> None:
    """Link every product of one ingredient to another (merge, ING-05), recording the admin
    who merged as the one who changed them last."""
    await session.execute(
        update(Product)
        .where(Product.ingredient_id == from_ingredient_id)
        .values(ingredient_id=to_ingredient_id, updated_by=actor_id, updated_at=now)
    )


async def for_ingredients(
    session: AsyncSession, ingredient_ids: Iterable[str]
) -> dict[str, list[Product]]:
    """The products per ingredient id (ingredients without products are missing)."""
    ids = set(ingredient_ids)
    products: dict[str, list[Product]] = defaultdict(list)
    if ids:
        result = await session.execute(select(Product).where(Product.ingredient_id.in_(ids)))
        for row in result.scalars():
            products[row.ingredient_id].append(row)
    return products
