"""Shopping lists: the Lists home, drafts with meals, extra items and hidden lines, copies
(LIST-01..10, LIST-13..15, CPL-02/03, VIS-03/06, UI-02)."""

from typing import Annotated

from fastapi import APIRouter, Header, Path, Response, status

from app.api.deps import CurrentUser, Media, Now
from app.core import etags
from app.db.session import ReadSession, WriteSession
from app.domain.lists import LINE_KEY_MAX_LENGTH, LINE_KEY_PATTERN, ListStatus
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.lists import (
    ExtraItemCreate,
    ExtraItemUpdate,
    ListCopyResult,
    ListCreate,
    ListDetail,
    ListMealAdd,
    ListMealUpdate,
    ListScope,
    ListSummary,
    ListUpdate,
)
from app.services import lists

router = APIRouter(prefix="/api/lists", tags=["lists"], responses=ERROR_RESPONSES)

LineKey = Annotated[
    str,
    Path(
        max_length=LINE_KEY_MAX_LENGTH,
        pattern=LINE_KEY_PATTERN,
        description="`i:<ingredient_id>` or `x:<extra_id>`, as in `ListLine.key`.",
    ),
]


@router.get("")
async def list_lists(
    principal: CurrentUser,
    session: ReadSession,
    scope: ListScope = "mine",
    status: ListStatus | None = None,
) -> list[ListSummary]:
    """The lists for the Lists home, most recently edited first. `mine`: your lists and those
    your partner shares with you; `others`: other lists you may see (read-only; public owners'
    lists and your partner's unshared ones), without the owners you switched off in your list
    filter chips (`filter_hidden.lists`). Without `status`: drafts and lists being shopped."""
    return await lists.list_lists(session, principal, scope=scope, status=status)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_list(
    body: ListCreate, principal: CurrentUser, session: WriteSession, media: Media, now: Now
) -> ListDetail:
    """A new draft of yours; it is shared with your partner if you have one."""
    return await lists.create_list(session, media, principal, body, now=now)


@router.get(
    "/{list_id}",
    response_model=ListDetail,
    responses={status.HTTP_304_NOT_MODIFIED: {"description": "Unchanged since the given ETag"}},
)
async def get_list(
    list_id: str,
    principal: CurrentUser,
    session: ReadSession,
    media: Media,
    now: Now,
    if_none_match: Annotated[str | None, Header(max_length=1000)] = None,
) -> Response:
    """A list you can see (404 otherwise), with a weak `ETag` over the response as you see it;
    send it back as `If-None-Match` to get a 304 without a body while nothing changed."""
    detail = await lists.get_list(session, media, principal, list_id, now=now)
    body = detail.model_dump_json().encode()
    etag = etags.weak_etag(body)
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    if etags.matches(if_none_match, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


@router.patch("/{list_id}")
async def update_list(
    list_id: str,
    body: ListUpdate,
    principal: CurrentUser,
    session: WriteSession,
    media: Media,
    now: Now,
) -> ListDetail:
    """Rename a list you may edit; switch sharing with your partner on your own list."""
    return await lists.update_list(session, media, principal, list_id, body, now=now)


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_list(list_id: str, principal: CurrentUser, session: WriteSession) -> None:
    """Delete your list, whatever its state."""
    await lists.delete_list(session, principal, list_id)


@router.post("/{list_id}/copy", status_code=status.HTTP_201_CREATED)
async def copy_list(
    list_id: str, principal: CurrentUser, session: WriteSession, media: Media, now: Now
) -> ListCopyResult:
    """Copy a list you can see into a new draft of yours; meals that no longer exist or that
    you cannot see are left out and counted."""
    return await lists.copy_list(session, media, principal, list_id, now=now)


@router.post("/{list_id}/meals")
async def add_list_meal(
    list_id: str,
    body: ListMealAdd,
    principal: CurrentUser,
    session: WriteSession,
    media: Media,
    now: Now,
) -> ListDetail:
    """Add a meal you can see; if it is already on the list, its servings rise instead."""
    return await lists.add_meal(session, media, principal, list_id, body, now=now)


@router.patch("/{list_id}/meals/{list_meal_id}")
async def update_list_meal(
    list_id: str,
    list_meal_id: str,
    body: ListMealUpdate,
    principal: CurrentUser,
    session: WriteSession,
    media: Media,
    now: Now,
) -> ListDetail:
    """Set the servings of a meal on the list."""
    return await lists.update_meal(session, media, principal, list_id, list_meal_id, body, now=now)


@router.delete("/{list_id}/meals/{list_meal_id}")
async def remove_list_meal(
    list_id: str,
    list_meal_id: str,
    principal: CurrentUser,
    session: WriteSession,
    media: Media,
    now: Now,
) -> ListDetail:
    """Take a meal off the list (also one that is no longer available)."""
    return await lists.remove_meal(session, media, principal, list_id, list_meal_id, now=now)


@router.post(
    "/{list_id}/extra-items",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_200_OK: {"model": ListDetail, "description": "Already added"}},
)
async def add_extra_item(
    list_id: str,
    body: ExtraItemCreate,
    response: Response,
    principal: CurrentUser,
    session: WriteSession,
    media: Media,
    now: Now,
) -> ListDetail:
    """Add an extra item: linked to an ingredient or free text. With an `id` already on this
    list nothing changes and the answer is 200 (safe to retry)."""
    detail, created = await lists.add_extra(session, media, principal, list_id, body, now=now)
    if not created:
        response.status_code = status.HTTP_200_OK
    return detail


@router.patch("/{list_id}/extra-items/{extra_id}")
async def update_extra_item(
    list_id: str,
    extra_id: str,
    body: ExtraItemUpdate,
    principal: CurrentUser,
    session: WriteSession,
    media: Media,
    now: Now,
) -> ListDetail:
    """Change an extra item; it keeps its kind (linked or free text)."""
    return await lists.update_extra(session, media, principal, list_id, extra_id, body, now=now)


@router.delete("/{list_id}/extra-items/{extra_id}")
async def delete_extra_item(
    list_id: str,
    extra_id: str,
    principal: CurrentUser,
    session: WriteSession,
    media: Media,
    now: Now,
) -> ListDetail:
    """Delete an extra item."""
    return await lists.delete_extra(session, media, principal, list_id, extra_id, now=now)


@router.post("/{list_id}/lines/{line_key}/hide")
async def hide_list_line(
    list_id: str,
    line_key: LineKey,
    principal: CurrentUser,
    session: WriteSession,
    media: Media,
    now: Now,
) -> ListDetail:
    """Remove a line for this list only (drafts; 409 `list.not_draft` otherwise)."""
    return await lists.set_line_hidden(
        session, media, principal, list_id, line_key, hidden=True, now=now
    )


@router.post("/{list_id}/lines/{line_key}/unhide")
async def unhide_list_line(
    list_id: str,
    line_key: LineKey,
    principal: CurrentUser,
    session: WriteSession,
    media: Media,
    now: Now,
) -> ListDetail:
    """Restore a removed line (drafts; 409 `list.not_draft` otherwise)."""
    return await lists.set_line_hidden(
        session, media, principal, list_id, line_key, hidden=False, now=now
    )
