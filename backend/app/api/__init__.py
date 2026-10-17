"""HTTP routers: thin layers that parse, call a service and return a schema.

Every route declares its response model; its function name becomes the OpenAPI operation ID.
Each router carries its full path prefix (`/api/...`) and is included without another one:
FastAPI resolves included prefixes per request only internally, and the request log takes the
route template from the matched route itself.
"""

from fastapi import APIRouter

from app.api import (
    admin,
    auth,
    couple,
    ingredients,
    lists,
    me,
    meals,
    media,
    recurring,
    reference,
    system,
    users,
    walking_order,
)

api_router = APIRouter()
for module in (
    system,
    auth,
    me,
    couple,
    users,
    reference,
    ingredients,
    meals,
    lists,
    recurring,
    walking_order,
    media,
    admin,
):
    api_router.include_router(module.router)
