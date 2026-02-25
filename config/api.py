from ninja import NinjaAPI

from inbox.api import router as inbox_router
from accounts.api import router as accounts_router
from projects.api import router as projects_router

api = NinjaAPI(
    title="FeatureRequest API",
    version="0.1.0",
    urls_namespace="feature_request_api",
)

api.add_router("", projects_router)
api.add_router("", inbox_router)
api.add_router("", accounts_router)


@api.get("/health", tags=["system"])
def health(request):
    return {"status": "ok"}
