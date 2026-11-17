"""Aggregation router for Corbel API v1 endpoints."""

from fastapi import APIRouter

from corbel.api.v1.endpoints import (
    ai,
    auth,
    datasets,
    governance,
    health,
    monitors,
    ontology,
    organizations,
    process,
    projects,
    query,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(organizations.router, prefix="/organizations", tags=["Organizations"])
api_router.include_router(projects.router, prefix="/projects", tags=["Projects"])
api_router.include_router(datasets.router, tags=["Data Intelligence & Profiling"])
api_router.include_router(ontology.router, tags=["Ontology Engine & Semantic Discovery"])
api_router.include_router(query.router, tags=["Structured Querying & Early AI Gateway"])
api_router.include_router(process.router, tags=["Process Intelligence & Event Mining"])
api_router.include_router(monitors.router, tags=["Adaptive Monitors & Exception Detection"])
api_router.include_router(ai.router, tags=["AI Infrastructure & Bounded State Machines"])
api_router.include_router(governance.router, tags=["Governed Investigation, Approvals & RAG"])
