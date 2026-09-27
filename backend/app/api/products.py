"""Products: barcodes linked to an ingredient (ING-04, BAR-04), the barcode lookup (BAR-02,
BAR-03) and pending Open Food Facts updates (BAR-06)."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, status

from app.api.deps import CurrentUser, Db, Now, OffRefresh
from app.db.session import ReadSession, WriteSession
from app.domain.catalog import BARCODE_INPUT_MAX_LENGTH
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.products import Product, ProductCreate, ProductLookup, ProductUpdate
from app.services import barcodes, off_refresh, products

router = APIRouter(prefix="/api/products", tags=["products"], responses=ERROR_RESPONSES)


@router.get("/lookup")
async def lookup_product(
    principal: CurrentUser,
    session: ReadSession,
    refresh: OffRefresh,
    database: Db,
    background: BackgroundTasks,
    now: Now,
    barcode: Annotated[str, Query(max_length=BARCODE_INPUT_MAX_LENGTH)],
) -> ProductLookup:
    """Look a scanned or typed barcode up: our own products first, then Open Food Facts (a
    proposal, not saved). 422 `invalid_format` for a barcode with a wrong check digit, 503
    `off.busy` while too many lookups wait for Open Food Facts."""
    result = await barcodes.lookup(session, refresh.off, principal, barcode)
    if result.product is not None:
        off_refresh.schedule_if_stale(background, refresh, database, [result.product], now=now)
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_product(
    body: ProductCreate, principal: CurrentUser, session: WriteSession, now: Now
) -> Product:
    """Add a product by hand or from an Open Food Facts proposal; its nutrition basis must be
    the ingredient's base unit."""
    return await products.create_product(session, principal, body, now=now)


@router.get("/{product_id}")
async def get_product(
    product_id: str,
    principal: CurrentUser,
    session: ReadSession,
    refresh: OffRefresh,
    database: Db,
    background: BackgroundTasks,
    now: Now,
) -> Product:
    """One product; a stale Open Food Facts product is refreshed after the response."""
    result = await products.get_product(session, product_id)
    off_refresh.schedule_if_stale(background, refresh, database, [result], now=now)
    return result


@router.patch("/{product_id}")
async def update_product(
    product_id: str, body: ProductUpdate, principal: CurrentUser, session: WriteSession, now: Now
) -> Product:
    """Change a product (anyone may); every field sent is marked user-edited."""
    return await products.update_product(session, principal, product_id, body, now=now)


@router.post("/{product_id}/pending-update/apply")
async def apply_pending_update(
    product_id: str, principal: CurrentUser, session: WriteSession, now: Now
) -> Product:
    """Take the newer Open Food Facts values (BAR-06); those fields are no longer
    user-edited. 409 `product.no_pending_update` if there are none."""
    return await products.apply_pending_update(session, principal, product_id, now=now)


@router.post("/{product_id}/pending-update/ignore")
async def ignore_pending_update(
    product_id: str, principal: CurrentUser, session: WriteSession, now: Now
) -> Product:
    """Keep the user's values (BAR-06); the same Open Food Facts version is not proposed
    again. 409 `product.no_pending_update` if there is nothing to ignore."""
    return await products.ignore_pending_update(session, principal, product_id, now=now)
