"""Aggregation router for Corbel API v1 endpoints."""

from fastapi import APIRouter

from corbel.api.v1.endpoints import auth, datasets, health, ontology, organizations, projects, query

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(organizations.router, prefix="/organizations", tags=["Organizations"])
api_router.include_router(projects.router, prefix="/projects", tags=["Projects"])
api_router.include_router(datasets.router, tags=["Data Intelligence & Profiling"])
api_router.include_router(ontology.router, tags=["Ontology Engine & Semantic Discovery"])
api_router.include_router(query.router, tags=["Structured Querying & Early AI Gateway"])
