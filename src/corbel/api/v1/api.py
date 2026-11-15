"""Aggregation router for Corbel API v1 endpoints."""

from fastapi import APIRouter

from corbel.api.v1.endpoints import auth, health, organizations, projects

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(organizations.router, prefix="/organizations", tags=["Organizations"])
api_router.include_router(projects.router, prefix="/projects", tags=["Projects"])
