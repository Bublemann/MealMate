"""Products: barcodes linked to an ingredient (ING-04, BAR-04)."""

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, Now
from app.db.session import ReadSession, WriteSession
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.products import Product, ProductCreate, ProductUpdate
from app.services import products

router = APIRouter(prefix="/api/products", tags=["products"], responses=ERROR_RESPONSES)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_product(
    body: ProductCreate, principal: CurrentUser, session: WriteSession, now: Now
) -> Product:
    """Add a product by hand; its nutrition basis must be the ingredient's base unit."""
    return await products.create_product(session, principal, body, now=now)


@router.get("/{product_id}")
async def get_product(product_id: str, principal: CurrentUser, session: ReadSession) -> Product:
    """One product."""
    return await products.get_product(session, product_id)


@router.patch("/{product_id}")
async def update_product(
    product_id: str, body: ProductUpdate, principal: CurrentUser, session: WriteSession, now: Now
) -> Product:
    """Change a product (anyone may); every field sent is marked user-edited."""
    return await products.update_product(session, principal, product_id, body, now=now)
