"""Shopping lists: the Lists home, drafts with meals, extra items and hidden lines, copies,
shopping mode with its ops, finishing, reopening, shopping again and the history (LIST-01..15,
SHOP, SYNC-05/06/08, CPL-02/03, VIS-03/06, UI-02)."""

from typing import Annotated

from fastapi import APIRouter, Header, Path, Response, status

from app.api.deps import CurrentUser, Db, ListResponses, Media, Now
from app.core import etags
from app.db.session import ReadSession, WriteSession
from app.domain.lists import LINE_KEY_MAX_LENGTH, LINE_KEY_PATTERN, ListStatus
from app.media import urls as media_urls
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
    OpsRequest,
    OpsResponse,
)
from app.services import lists, ops

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


@router.get("/history")
async def list_history(principal: CurrentUser, session: ReadSession) -> list[ListSummary]:
    """The done lists of your history, most recently finished first (at most 200): your own
    and those your partner shares with you (SHOP-05, CPL-02). Group them by the week of
    `finished_at` in your time zone."""
    return await lists.list_history(session, principal)


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
    database: Db,
    cache: ListResponses,
    media: Media,
    now: Now,
    if_none_match: Annotated[str | None, Header(max_length=1000)] = None,
) -> Response:
    """A list you can see (404 otherwise), with a weak `ETag` over the response as you see it;
    send it back as `If-None-Match` to get a 304 without a body while nothing changed. Polls
    are answered from a cache until something is written (PERF-02)."""

    async def build() -> bytes:
        detail = await lists.get_list(session, media, principal, list_id, now=now)
        return detail.model_dump_json().encode()

    key = (list_id, principal.user_id, media_urls.expiry(now))
    entry = await cache.get_or_build(key, database.write_generation, build)
    if etags.matches(if_none_match, entry.etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=entry.headers)
    return Response(content=entry.body, media_type="application/json", headers=entry.headers)


@router.patch("/{list_id}")
async def update_list(
    list_id: str,
    body: ListUpdate,
    principal: CurrentUser,
    session: WriteSession,
    media: Media,
    now: Now,
) -> ListDetail:
    """Rename a list you may edit; switch sharing with your partner on your own list. Not once
    it is done (409 `list.done`)."""
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


@router.post("/{list_id}/start-shopping")
async def start_shopping(
    list_id: str, principal: CurrentUser, session: WriteSession, media: Media, now: Now
) -> ListDetail:
    """Start shopping a draft you may edit (409 `list.not_draft` otherwise): its meals'
    ingredients are frozen, so later changes of meals and ingredients no longer affect it
    (LIST-11), and lines can be checked off."""
    return await lists.start_shopping(session, media, principal, list_id, now=now)


@router.post("/{list_id}/reopen")
async def reopen_list(
    list_id: str, principal: CurrentUser, session: WriteSession, media: Media, now: Now
) -> ListDetail:
    """Back to shopping, for a done list you may edit (409 `list.not_done` otherwise;
    SHOP-06)."""
    return await lists.reopen_list(session, media, principal, list_id, now=now)


@router.post("/{list_id}/shop-again", status_code=status.HTTP_201_CREATED)
async def shop_again(
    list_id: str, principal: CurrentUser, session: WriteSession, media: Media, now: Now
) -> ListCopyResult:
    """A new draft of yours from a done list you can see (409 `list.not_done` otherwise): the
    current versions of its meals with their servings, and its extra items, all unchecked;
    meals that no longer exist or that you cannot see are left out and counted (SHOP-06)."""
    return await lists.shop_again(session, media, principal, list_id, now=now)


@router.post("/{list_id}/ops")
async def apply_list_ops(
    list_id: str,
    body: OpsRequest,
    principal: CurrentUser,
    session: WriteSession,
    media: Media,
    now: Now,
) -> OpsResponse:
    """Apply the actions of shopping mode in order, in one transaction (plan § 5.8): check
    off, add, rename and delete free-text items, finish. Each op is applied once, however often
    it is sent (SYNC-05); the result of each and the list afterwards come back. The list must
    be one you may edit (404, 403 otherwise)."""
    return await ops.apply_ops(session, media, principal, list_id, body, now=now)


@router.post("/{list_id}/meals")
async def add_list_meal(
    list_id: str,
    body: ListMealAdd,
    principal: CurrentUser,
    session: WriteSession,
    media: Media,
    now: Now,
) -> ListDetail:
    """Add a meal you can see; if it is already on the list, its servings rise instead. In a
    draft or while shopping (a meal added while shopping is frozen at once); 409 `list.done`
    once the list is done, like every change of its meals and extra items."""
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
    list nothing changes and the answer is 200 (safe to retry). While shopping, the item is
    `new` on the list."""
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
