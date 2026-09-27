"""Meal photos behind signed URLs (VIS-05, plan § 5.10).

No bearer token: `<img>` tags cannot send one. The signature, issued only in meal responses
after the view check, is the permission.
"""

from typing import Annotated

import anyio
from fastapi import APIRouter, Query, Response

from app.api.deps import Media, Now
from app.core.errors import not_found
from app.media import urls
from app.schemas.errors import ERROR_RESPONSES

MEDIA_TYPE = "image/webp"
CACHE_CONTROL = f"private, max-age={urls.URL_LIFETIME_SECONDS}"

router = APIRouter(prefix=urls.MEDIA_PATH, tags=["media"], responses=ERROR_RESPONSES)


@router.get(
    "/{name}",
    response_class=Response,
    responses={
        200: {
            "content": {MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}},
            "description": "The WebP image",
        }
    },
)
async def get_media(
    name: str,
    media: Media,
    now: Now,
    exp: Annotated[str, Query(description="Expiry (Unix time), from the signed URL.")] = "",
    sig: Annotated[str, Query(description="Signature, from the signed URL.")] = "",
) -> Response:
    """A photo or thumbnail from a signed URL of a meal response. 404 `common.not_found` for
    an unknown name, a wrong or expired signature, or a deleted photo."""
    if not urls.is_valid(media.key, name, exp, sig, now=now):
        raise not_found()
    try:
        content = await anyio.Path(media.path(name)).read_bytes()
    except FileNotFoundError:
        raise not_found() from None
    return Response(content, media_type=MEDIA_TYPE, headers={"Cache-Control": CACHE_CONTROL})
