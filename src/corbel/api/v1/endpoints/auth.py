"""Authentication API endpoints: registration, login, token refresh, and user profile."""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.core.database import get_db_session
from corbel.domains.tenancy.dependencies import get_current_user
from corbel.domains.tenancy.models import User
from corbel.domains.tenancy.schemas import (
    RefreshTokenRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from corbel.domains.tenancy.service import TenancyService

router = APIRouter()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="User Registration",
    description="Register a new user account with validated email and secure bcrypt password hashing.",
)
async def register(
    req: UserRegisterRequest,
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Create a new user identity."""
    service = TenancyService(session)
    user = await service.register_user(req)
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="User Login",
    description="Authenticate user credentials and receive cryptographically signed JWT access and refresh tokens.",
)
async def login(
    req: UserLoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Authenticate and obtain JWT access token with persistent session."""
    service = TenancyService(session)
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return await service.authenticate_user(req, ip_address=ip_address, user_agent=user_agent)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh Access Token",
    description="Generate a fresh access token using a valid, unexpired refresh token.",
)
async def refresh_token(
    req: RefreshTokenRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Issue a new access token from refresh token."""
    service = TenancyService(session)
    return await service.refresh_access_token(req.refresh_token)


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Current User Profile",
    description="Retrieve the authenticated user's profile information.",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return currently authenticated user."""
    return UserResponse.model_validate(current_user)


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="User Logout",
    description="Terminate active user session and revoke outstanding tokens.",
)
async def logout(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Logout current session and revoke outstanding refresh tokens."""
    service = TenancyService(session)
    session_id = getattr(current_user, "active_session_id", None)
    await service.terminate_session(user_id=current_user.id, session_id=session_id)
    return {"message": "Session terminated successfully"}
