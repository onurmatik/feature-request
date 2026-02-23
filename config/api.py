from ninja import NinjaAPI

api = NinjaAPI(
    title="FeatureRequest API",
    version="0.1.0",
    urls_namespace="feature_request_api",
)


@api.get("/health", tags=["system"])
def health(request):
    return {"status": "ok"}
