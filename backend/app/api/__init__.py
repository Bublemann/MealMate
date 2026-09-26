"""HTTP routers: thin layers that parse, call a service and return a schema.

Every route declares its response model; its function name becomes the OpenAPI operation ID.
Each router carries its full path prefix (`/api/...`) and is included without another one:
FastAPI resolves included prefixes per request only internally, and the request log takes the
route template from the matched route itself.
"""

from fastapi import APIRouter

from app.api import system

api_router = APIRouter()
api_router.include_router(system.router)
