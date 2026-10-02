"""Meals: list, detail, create, edit, delete, copy and photo (MEAL-01..10, VIS-04/05)."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from pydantic import StringConstraints

from app.api.deps import CurrentUser, Media, Now, limit_uploads
from app.db.session import ReadSession, WriteSession
from app.media.images import MAX_UPLOAD_BYTES
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.meals import Meal, MealCreate, MealSummary, MealUpdate
from app.schemas.reference import Tag
from app.services import meals

router = APIRouter(prefix="/api/meals", tags=["meals"], responses=ERROR_RESPONSES)

# A cuisine or tag id (a UUID). The list takes up to 100 of them, more than anyone ticks.
FilterId = Annotated[str, StringConstraints(max_length=36)]


@router.get("")
async def list_meals(
    principal: CurrentUser,
    session: ReadSession,
    media: Media,
    now: Now,
    q: Annotated[str | None, Query(max_length=100)] = None,
    cuisine_id: Annotated[list[FilterId] | None, Query(max_length=100)] = None,
    tag_id: Annotated[list[FilterId] | None, Query(max_length=100)] = None,
    owner_ids: Annotated[list[str] | None, Query(max_length=500)] = None,
) -> list[MealSummary]:
    """The meals you can see, A-Z in dictionary order (Ä sorts as A). `q` searches names, tags
    and cuisines ignoring case and umlauts. `cuisine_id` and `tag_id` are repeatable: a meal
    matches if its cuisine is any of the given ones and it has every given tag. Without
    `owner_ids`, owners you unticked in your user filter on Meals (`filter_hidden.meals`) are
    left out; with `owner_ids` (repeatable), only those owners' meals are listed."""
    return await meals.list_meals(
        session,
        media,
        principal,
        query=q,
        cuisine_ids=cuisine_id or [],
        tag_ids=tag_id or [],
        owner_ids=owner_ids,
        now=now,
    )


@router.get("/tags")
async def list_meal_tags(principal: CurrentUser, session: ReadSession) -> list[Tag]:
    """The tags on the meals you can see, A-Z, for the tag filter. Unlike `/api/tags` it has no
    limit and ignores your filter chips."""
    return await meals.list_meal_tags(session, principal)


@router.get("/recent")
async def list_recent_meals(
    principal: CurrentUser, session: ReadSession, media: Media, now: Now
) -> list[MealSummary]:
    """Up to 10 meals you recently added to lists, most recent first, as far as you can still
    see them (the "recently used" meals of the meal picker)."""
    return await meals.recent_meals(session, media, principal, now=now)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_meal(
    body: MealCreate, principal: CurrentUser, session: WriteSession, media: Media, now: Now
) -> Meal:
    """Add a meal of your own; only the name is required."""
    return await meals.create_meal(session, media, principal, body, now=now)


@router.get("/{meal_id}")
async def get_meal(
    meal_id: str, principal: CurrentUser, session: ReadSession, media: Media, now: Now
) -> Meal:
    """A meal you can see (404 otherwise), with nutrition and signed photo URLs."""
    return await meals.get_meal(session, media, principal, meal_id, now=now)


@router.patch("/{meal_id}")
async def update_meal(
    meal_id: str,
    body: MealUpdate,
    principal: CurrentUser,
    session: WriteSession,
    media: Media,
    now: Now,
) -> Meal:
    """Change your meal; `tags` and `ingredients` replace the whole list."""
    return await meals.update_meal(session, media, principal, meal_id, body, now=now)


@router.delete("/{meal_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_meal(
    meal_id: str, principal: CurrentUser, session: WriteSession, media: Media, now: Now
) -> None:
    """Delete your meal; on lists it becomes "no longer available" (it keeps its ingredients
    there until it is removed)."""
    await meals.delete_meal(session, media, principal, meal_id, now=now)


@router.post("/{meal_id}/copy", status_code=status.HTTP_201_CREATED)
async def copy_meal(
    meal_id: str, principal: CurrentUser, session: WriteSession, media: Media, now: Now
) -> Meal:
    """Copy a meal you can see to your meals, with its own copy of the photo ("based on")."""
    return await meals.copy_meal(session, media, principal, meal_id, now=now)


@router.put("/{meal_id}/photo", dependencies=[Depends(limit_uploads)])
async def upload_meal_photo(
    meal_id: str,
    file: Annotated[UploadFile, File(description="A JPEG, PNG or WebP image of at most 10 MB.")],
    principal: CurrentUser,
    session: WriteSession,
    media: Media,
    now: Now,
) -> Meal:
    """Set the photo of your meal (at most 20 uploads per 10 minutes). It is rotated upright,
    re-encoded without metadata and stored with a thumbnail; errors: 413 `media.too_large`,
    415 `media.unsupported_type`, 422 `media.too_many_pixels`."""
    # One byte more than allowed is enough to know it is too large.
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    return await meals.set_photo(session, media, principal, meal_id, data, now=now)


@router.delete("/{meal_id}/photo", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_meal_photo(
    meal_id: str, principal: CurrentUser, session: WriteSession, media: Media, now: Now
) -> None:
    """Remove the photo of your meal."""
    await meals.delete_photo(session, media, principal, meal_id, now=now)
