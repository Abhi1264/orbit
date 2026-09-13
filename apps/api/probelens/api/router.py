from fastapi import APIRouter

from probelens.api.routes import (
    ai,
    analytics,
    anomalies,
    auth,
    comments,
    decisions,
    experiments,
    investigations,
    ops,
    releases,
    saved,
    search,
    system,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(analytics.router)
api_router.include_router(saved.router)
api_router.include_router(anomalies.router)
api_router.include_router(investigations.router)
api_router.include_router(experiments.router)
api_router.include_router(comments.router)
api_router.include_router(releases.router)
api_router.include_router(ops.router)
api_router.include_router(decisions.router)
api_router.include_router(search.router)
api_router.include_router(system.router)
api_router.include_router(ai.router)
