"""Reference data: categories, units, cuisines, tags (REF-01..04)."""

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, Now
from app.db.session import ReadSession, WriteSession
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.reference import Category, Cuisine, CuisineCreate, Tag, UnitInfo
from app.services import reference

router = APIRouter(prefix="/api", tags=["reference"], responses=ERROR_RESPONSES)


@router.get("/categories")
async def list_categories(principal: CurrentUser, session: ReadSession) -> list[Category]:
    """Every category in the shop's walking order, deleted ones included: lists being shopped and
    done lists still show them (D-30). A deleted one comes after the category that took over its
    place."""
    return await reference.list_categories(session)


@router.get("/units")
async def list_units(principal: CurrentUser) -> list[UnitInfo]:
    """All units in display order, with their kind and the base units they fit."""
    return reference.list_units()


@router.get("/cuisines")
async def list_cuisines(principal: CurrentUser, session: ReadSession) -> list[Cuisine]:
    """Seeded cuisines in their fixed order, then the ones users added, by name."""
    return await reference.list_cuisines(session)


@router.post(
    "/cuisines",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_200_OK: {
            "model": Cuisine,
            "description": "A cuisine with this name (ignoring case and umlauts) exists already",
        }
    },
)
async def create_cuisine(
    body: CuisineCreate,
    response: Response,
    principal: CurrentUser,
    session: WriteSession,
    now: Now,
) -> Cuisine:
    """Add a cuisine as plain text (201), or get the existing one with that name (200)."""
    result = await reference.create_cuisine(session, principal, body.name, now=now)
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return result.cuisine


@router.get("/tags")
async def list_tags(
    principal: CurrentUser,
    session: ReadSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> list[Tag]:
    """Tags for autocomplete: at most 20 whose name contains `q`, prefix matches first."""
    return await reference.list_tags(session, q)
