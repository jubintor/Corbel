"""TenancyService handling user registration, authentication, organizations, and projects."""

import secrets
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.core.config import get_settings
from corbel.core.exceptions import CorbelException
from corbel.domains.governance.audit import AuditService
from corbel.domains.tenancy.exceptions import (
    CrossTenantViolationException,
    InsufficientPermissionException,
    InvalidCredentialsException,
    MembershipInactiveException,
    NotOrganizationMemberException,
    OrganizationNotFoundException,
    OrganizationSuspendedException,
    ProjectNotFoundException,
    UserAlreadyExistsException,
)
from corbel.domains.tenancy.models import (
    MembershipStatus,
    Organization,
    OrganizationMember,
    OrgRole,
    OrgStatus,
    Project,
    ProjectMember,
    ProjectRole,
    ProjectStatus,
    RateLimitBucket,
    RefreshToken,
    SessionStatus,
    User,
    UserSession,
)
from corbel.domains.tenancy.rate_limiter import RateLimiter, RateLimitExceededException
from corbel.domains.tenancy.schemas import (
    MemberAddRequest,
    OrganizationCreateRequest,
    OrganizationUpdateRequest,
    OrganizationWithRoleResponse,
    ProjectCreateRequest,
    ProjectUpdateRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    slugify,
)
from corbel.domains.tenancy.security import (
    DUMMY_BCRYPT_HASH,
    create_access_token,
    create_refresh_token,
    decode_token,
    decrypt_token,
    encrypt_token,
    hash_password_async,
    hash_token,
    verify_password_async,
)


class TenancyService:
    """Core domain service for user authentication, organizations, and tenant-scoped workspaces."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit_service = AuditService(session)

    # ==========================================================================
    # Authentication & User Management
    # ==========================================================================

    async def register_user(self, req: UserRegisterRequest, ip_address: str | None = None) -> User:
        """Register a new user account with hashed password and concurrency safety (P2-LIM-004, P2-LIM-008)."""
        settings = get_settings()
        if ip_address:
            rate_limiter = RateLimiter(self.session)
            retry_after = await rate_limiter.check_and_record(
                f"reg:ip:{ip_address}",
                max_requests=settings.RATE_LIMIT_REGISTER_PER_MINUTE,
                window_seconds=60,
            )
            if retry_after:
                raise RateLimitExceededException(
                    message=f"Too many registration attempts. Please retry in {retry_after} seconds.",
                    retry_after=retry_after,
                )

        # Check if user already exists
        stmt = select(User).where(func.lower(User.email) == req.email.lower())
        result = await self.session.execute(stmt)
        if result.scalar_one_or_none() is not None:
            raise UserAlreadyExistsException("A user with this email address is already registered.")

        hashed = await hash_password_async(req.password)
        user = User(
            id=uuid.uuid4(),
            email=req.email.lower(),
            hashed_password=hashed,
            full_name=req.full_name,
            is_active=True,
        )
        self.session.add(user)
        try:
            await self.session.commit()
            await self.session.refresh(user)
            return user
        except IntegrityError as exc:
            await self.session.rollback()
            raise UserAlreadyExistsException("A user with this email address is already registered.") from exc

    async def authenticate_user(
        self,
        req: UserLoginRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenResponse:
        """Authenticate user credentials and return access and refresh JWT tokens with persistent session (P2-LIM-003, P2-LIM-004)."""
        settings = get_settings()
        rate_limiter = RateLimiter(self.session)
        email_clean = req.email.strip().lower()

        client_ip = ip_address or "127.0.0.1"

        # 1. Enforce IP-based rate limiting to prevent brute force and bcrypt CPU exhaustion
        ip_retry = await rate_limiter.check_and_record(
            f"login:ip:{client_ip}",
            max_requests=settings.RATE_LIMIT_LOGIN_PER_MINUTE,
            window_seconds=60,
        )
        if ip_retry:
            raise RateLimitExceededException(
                message=f"Too many requests from this IP address. Please retry in {ip_retry} seconds.",
                retry_after=ip_retry,
            )

        # 2. Check combined Account + IP lockout to prevent cross-IP denial of service (P2-LIM-004)
        account_ip_key = f"login:account_ip:{email_clean}:{client_ip}"
        acc_retry = await rate_limiter.is_blocked(account_ip_key)
        if acc_retry:
            raise RateLimitExceededException(
                message=f"Account temporarily locked for this IP due to excessive failed attempts. Please retry in {acc_retry} seconds.",
                retry_after=acc_retry,
            )

        # 3. Constant-time credential verification (P2-LIM-003)
        stmt = select(User).where(func.lower(User.email) == email_clean)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()

        target_hash = user.hashed_password if user is not None else DUMMY_BCRYPT_HASH
        password_matches = await verify_password_async(req.password, target_hash)

        if user is None or not password_matches:
            # Record failed login attempt for this account from this IP (P2-LIM-004)
            await rate_limiter.record_failure(
                account_ip_key,
                window_seconds=settings.RATE_LIMIT_LOCKOUT_MINUTES * 60,
                lockout_threshold=settings.RATE_LIMIT_LOGIN_FAILURES_LOCKOUT,
                lockout_seconds=settings.RATE_LIMIT_LOCKOUT_MINUTES * 60,
            )
            await self.session.commit()
            raise InvalidCredentialsException("Invalid email or password")

        if not user.is_active:
            raise InvalidCredentialsException("User account is inactive. Please contact your administrator.")

        # On successful authentication, reset failed attempts counter for this account and IP (P2-LIM-004)
        await rate_limiter.reset(account_ip_key)

        now_utc = datetime.now(UTC)
        session_expires_at = now_utc + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        # 1. Create and persist UserSession
        session_id = uuid.uuid4()
        user_session = UserSession(
            id=session_id,
            user_id=user.id,
            status=SessionStatus.ACTIVE.value,
            created_at=now_utc,
            expires_at=session_expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.session.add(user_session)

        # 2. Create access token bound to session_id
        access_token = create_access_token(
            user_id=user.id,
            email=user.email,
            session_id=session_id,
        )

        # 3. Create and persist initial refresh token in the session
        token_id = uuid.uuid4()
        refresh_token, _, _, _, refresh_expires_at = create_refresh_token(
            user_id=user.id,
            email=user.email,
            session_id=session_id,
            family_id=session_id,
            token_id=token_id,
        )

        db_token = RefreshToken(
            id=token_id,
            session_id=session_id,
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            family_id=session_id,
            is_revoked=False,
            expires_at=refresh_expires_at,
            encrypted_replacement_token=None,
        )
        self.session.add(db_token)
        await self.session.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def refresh_access_token(
        self,
        refresh_token: str,
        idempotency_key: str | None = None,
    ) -> TokenResponse:
        """Issue a new access token and rotated refresh token with collision recovery (P2-LIM-001)."""
        payload = decode_token(refresh_token, expected_type="refresh")
        user_id_str = payload.get("sub")
        jti_str = payload.get("jti")
        sid_str = payload.get("sid")

        if not user_id_str or not jti_str:
            raise InvalidCredentialsException("Malformed refresh token claims")

        try:
            token_id = uuid.UUID(jti_str)
            user_id = uuid.UUID(user_id_str)
        except ValueError as exc:
            raise InvalidCredentialsException("Invalid token identifier format") from exc

        # 1. Acquire exclusive row lock on RefreshToken to coordinate concurrent rotations
        stmt = (
            select(RefreshToken)
            .where(RefreshToken.id == token_id)
            .with_for_update()
        )
        res = await self.session.execute(stmt)
        token_record = res.scalar_one_or_none()
        if token_record is None:
            raise InvalidCredentialsException("Refresh token not found or already purged")

        # Verify token hash to prevent forged token IDs
        if token_record.token_hash != hash_token(refresh_token):
            raise InvalidCredentialsException("Invalid refresh token hash")

        # 2. Acquire exclusive row lock on associated UserSession
        session_id = token_record.session_id or (uuid.UUID(sid_str) if sid_str else token_record.family_id)
        session_stmt = (
            select(UserSession)
            .where(UserSession.id == session_id)
            .with_for_update()
        )
        session_res = await self.session.execute(session_stmt)
        session_record = session_res.scalar_one_or_none()

        now_utc = datetime.now(UTC)
        settings = get_settings()

        # 3. REPLAY vs IDEMPOTENT RETRY HANDLING (P2-LIM-001)
        if token_record.is_revoked:
            # Check if this is within the 15-second grace window
            is_recent_rotation = (
                token_record.replaced_by is not None
                and token_record.revoked_at is not None
                and (now_utc - token_record.revoked_at) <= timedelta(seconds=15)
            )

            # Idempotency protocol: Only return replacement if supplied key matches the stored hash
            has_matching_key = (
                idempotency_key is not None
                and token_record.idempotency_key_hash is not None
                and hash_token(idempotency_key) == token_record.idempotency_key_hash
            )

            if (
                is_recent_rotation
                and session_record is not None
                and session_record.status == SessionStatus.ACTIVE.value
                and has_matching_key
                and token_record.encrypted_replacement_token
            ):
                # Legitimate client retry: same token, same idempotency key, active session
                recovered_refresh = decrypt_token(token_record.encrypted_replacement_token)
                fresh_access_token = create_access_token(
                    user_id=user_id,
                    email=payload.get("email", ""),
                    session_id=session_record.id,
                )
                return TokenResponse(
                    access_token=fresh_access_token,
                    refresh_token=recovered_refresh,
                    token_type="bearer",
                    expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                )

            # Replay / Theft Attempt or Expired Window: Revoke family and session!
            if session_record is not None:
                session_record.status = SessionStatus.REVOKED.value
                session_record.revoked_at = now_utc

            await self.session.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == token_record.family_id)
                .values(is_revoked=True, revoked_at=now_utc)
            )
            await self.session.commit()

            if is_recent_rotation and idempotency_key is None:
                raise InvalidCredentialsException(
                    "Refresh token reuse detected without valid idempotency key. Session revoked."
                )
            elif is_recent_rotation and not has_matching_key:
                raise InvalidCredentialsException(
                    "Refresh token reuse detected with mismatched idempotency key. Session revoked."
                )
            else:
                raise InvalidCredentialsException(
                    "Refresh token reuse detected. All tokens in this session have been revoked."
                )

        # 4. Check session validity
        if session_record is None or session_record.status != SessionStatus.ACTIVE.value:
            token_record.is_revoked = True
            token_record.revoked_at = now_utc
            await self.session.commit()
            raise InvalidCredentialsException("Session has been terminated or revoked")

        if session_record.expires_at < now_utc:
            session_record.status = SessionStatus.EXPIRED.value
            token_record.is_revoked = True
            token_record.revoked_at = now_utc
            await self.session.commit()
            raise InvalidCredentialsException("Session has expired")

        # 5. Check token expiration
        if token_record.expires_at < now_utc:
            token_record.is_revoked = True
            token_record.revoked_at = now_utc
            await self.session.commit()
            raise InvalidCredentialsException("Refresh token has expired")

        # 6. Check user status
        user = await self.session.get(User, user_id)
        if user is None or not user.is_active:
            raise InvalidCredentialsException("User account not found or inactive")

        # 7. Valid single-use rotation with encrypted replacement caching (P2-LIM-001)
        new_token_id = uuid.uuid4()

        # Issue replacement refresh token
        new_refresh_str, _, _, _, new_expires_at = create_refresh_token(
            user_id=user.id,
            email=user.email,
            session_id=session_record.id,
            family_id=token_record.family_id,
            token_id=new_token_id,
        )

        if idempotency_key:
            token_record.idempotency_key_hash = hash_token(idempotency_key)
        else:
            token_record.idempotency_key_hash = hash_token(secrets.token_urlsafe(32))

        token_record.is_revoked = True
        token_record.revoked_at = now_utc
        token_record.replaced_by = new_token_id
        token_record.encrypted_replacement_token = encrypt_token(new_refresh_str)

        child_record = RefreshToken(
            id=new_token_id,
            session_id=session_record.id,
            user_id=user.id,
            token_hash=hash_token(new_refresh_str),
            family_id=token_record.family_id,
            is_revoked=False,
            expires_at=new_expires_at,
            encrypted_replacement_token=None,
        )
        self.session.add(child_record)

        # Issue replacement access token bound to the active session
        new_access_token = create_access_token(
            user_id=user.id,
            email=user.email,
            session_id=session_record.id,
        )

        await self.session.commit()

        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_str,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def terminate_session(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID | None = None,
    ) -> None:
        """Revoke server-side session and all associated refresh tokens."""
        now_utc = datetime.now(UTC)
        if session_id:
            await self.session.execute(
                update(UserSession)
                .where(UserSession.id == session_id, UserSession.user_id == user_id)
                .values(status=SessionStatus.REVOKED.value, revoked_at=now_utc)
            )
            await self.session.execute(
                update(RefreshToken)
                .where(RefreshToken.session_id == session_id)
                .values(is_revoked=True, revoked_at=now_utc)
            )
        else:
            await self.session.execute(
                update(UserSession)
                .where(UserSession.user_id == user_id, UserSession.status == SessionStatus.ACTIVE.value)
                .values(status=SessionStatus.REVOKED.value, revoked_at=now_utc)
            )
            await self.session.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == user_id, RefreshToken.is_revoked.is_(False))
                .values(is_revoked=True, revoked_at=now_utc)
            )
        await self.session.commit()

    # ==========================================================================
    # Organization Management
    # ==========================================================================

    async def create_organization(self, user_id: uuid.UUID, req: OrganizationCreateRequest) -> Organization:
        """Create a new organization and grant creator ORG_ADMIN membership with uniqueness protection (P2-LIM-008)."""
        slug = req.slug or slugify(req.name)
        base_slug = slug
        counter = 1
        while True:
            stmt = select(Organization).where(Organization.slug == slug)
            res = await self.session.execute(stmt)
            if res.scalar_one_or_none() is None:
                break
            slug = f"{base_slug}-{counter}"
            counter += 1

        org = Organization(
            id=uuid.uuid4(),
            name=req.name,
            slug=slug,
            status=OrgStatus.ACTIVE.value,
        )
        self.session.add(org)
        await self.session.flush()

        # Creator becomes ORG_ADMIN
        membership = OrganizationMember(
            id=uuid.uuid4(),
            organization_id=org.id,
            user_id=user_id,
            role=OrgRole.ORG_ADMIN.value,
            status=MembershipStatus.ACTIVE.value,
        )
        self.session.add(membership)
        await self.audit_service.log_event(
            organization_id=org.id,
            project_id=None,
            actor_id=str(user_id),
            action_type="ORGANIZATION_CREATED",
            affected_entity_type="Organization",
            affected_entity_id=str(org.id),
            execution_context={"name": org.name, "slug": slug},
        )
        try:
            await self.session.commit()
            await self.session.refresh(org)
            return org
        except IntegrityError as exc:
            await self.session.rollback()
            raise CorbelException(
                message=f"Organization slug '{slug}' already exists. Please choose a different name or slug.",
                status_code=409,
                error_code="SLUG_CONFLICT",
            ) from exc

    async def get_user_organizations(self, user_id: uuid.UUID) -> list[OrganizationWithRoleResponse]:
        """List all organizations the user is a member of, along with their role and status."""
        stmt = (
            select(Organization, OrganizationMember)
            .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
            .where(OrganizationMember.user_id == user_id)
            .order_by(Organization.created_at.desc())
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        orgs: list[OrganizationWithRoleResponse] = []
        for org, member in rows:
            orgs.append(
                OrganizationWithRoleResponse(
                    id=org.id,
                    name=org.name,
                    slug=org.slug,
                    status=org.status,
                    role=member.role,
                    membership_status=member.status,
                    created_at=org.created_at,
                )
            )
        return orgs

    async def get_organization(self, org_id: uuid.UUID, user_id: uuid.UUID) -> Organization:
        """Retrieve organization details, verifying that the user has active membership."""
        stmt = (
            select(Organization)
            .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
            .where(
                Organization.id == org_id,
                OrganizationMember.user_id == user_id,
            )
        )
        result = await self.session.execute(stmt)
        org = result.scalar_one_or_none()
        if org is None:
            raise NotOrganizationMemberException(org_id)

        if org.status == OrgStatus.SUSPENDED.value:
            raise OrganizationSuspendedException(org_id)

        return org

    async def update_organization(
        self,
        org_id: uuid.UUID,
        actor_id: uuid.UUID,
        req: OrganizationUpdateRequest,
    ) -> Organization:
        """Update organization details (requires ORG_ADMIN)."""
        await self.verify_membership(org_id, actor_id, required_roles=[OrgRole.ORG_ADMIN])

        org = await self.session.get(Organization, org_id)
        if org is None:
            raise OrganizationNotFoundException(org_id)

        if req.name is not None:
            org.name = req.name
        if req.status is not None:
            org.status = req.status.value

        await self.session.commit()
        await self.session.refresh(org)
        return org

    # ==========================================================================
    # Membership Management
    # ==========================================================================

    async def verify_membership(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        required_roles: list[OrgRole] | None = None,
    ) -> OrganizationMember:
        """Verify that user is an ACTIVE member of the active organization, checking role requirements."""
        stmt = (
            select(OrganizationMember, Organization)
            .join(Organization, Organization.id == OrganizationMember.organization_id)
            .where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user_id,
            )
        )
        result = await self.session.execute(stmt)
        row = result.first()

        if row is None:
            raise NotOrganizationMemberException(org_id)

        membership: OrganizationMember = row[0]
        org: Organization = row[1]

        if membership.status != MembershipStatus.ACTIVE.value:
            raise MembershipInactiveException(membership.status)

        if org.status == OrgStatus.SUSPENDED.value:
            raise OrganizationSuspendedException(org_id)

        if required_roles and membership.role not in [r.value for r in required_roles]:
            raise InsufficientPermissionException(required_role=", ".join(r.value for r in required_roles))

        return membership

    async def list_organization_members(
        self,
        org_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> Sequence[tuple[OrganizationMember, User]]:
        """List all members of an organization."""
        await self.verify_membership(org_id, actor_id)

        stmt = (
            select(OrganizationMember, User)
            .join(User, User.id == OrganizationMember.user_id)
            .where(OrganizationMember.organization_id == org_id)
            .order_by(OrganizationMember.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.tuples().all()

    async def add_organization_member(
        self,
        org_id: uuid.UUID,
        actor_id: uuid.UUID,
        req: MemberAddRequest,
    ) -> OrganizationMember:
        """Add a user to the organization by email (requires ORG_ADMIN)."""
        await self.verify_membership(org_id, actor_id, required_roles=[OrgRole.ORG_ADMIN])

        stmt = select(User).where(func.lower(User.email) == req.email.lower())
        res = await self.session.execute(stmt)
        target_user = res.scalar_one_or_none()
        if target_user is None:
            raise InvalidCredentialsException(f"User with email '{req.email}' not found")

        # Check if already a member
        member_stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == target_user.id,
        )
        existing = (await self.session.execute(member_stmt)).scalar_one_or_none()
        if existing is not None:
            if existing.status == MembershipStatus.ACTIVE.value:
                raise CrossTenantViolationException(f"User '{req.email}' is already an active member of this organization")
            # Reactivate if previously suspended or revoked
            existing.status = MembershipStatus.ACTIVE.value
            existing.role = req.role.value
            await self.audit_service.log_event(
                organization_id=org_id,
                project_id=None,
                actor_id=str(actor_id),
                action_type="MEMBER_REACTIVATED",
                affected_entity_type="OrganizationMember",
                affected_entity_id=str(existing.id),
                execution_context={"target_user_id": str(target_user.id), "role": req.role.value},
            )
            try:
                await self.session.commit()
                await self.session.refresh(existing)
                return existing
            except Exception:
                await self.session.rollback()
                raise

        new_member = OrganizationMember(
            id=uuid.uuid4(),
            organization_id=org_id,
            user_id=target_user.id,
            role=req.role.value,
            status=MembershipStatus.ACTIVE.value,
        )
        self.session.add(new_member)
        await self.audit_service.log_event(
            organization_id=org_id,
            project_id=None,
            actor_id=str(actor_id),
            action_type="MEMBER_ADDED",
            affected_entity_type="OrganizationMember",
            affected_entity_id=str(new_member.id),
            execution_context={"target_user_id": str(target_user.id), "role": req.role.value},
        )
        await self.session.commit()
        await self.session.refresh(new_member)
        return new_member

    async def update_member_role(
        self,
        org_id: uuid.UUID,
        actor_id: uuid.UUID,
        target_user_id: uuid.UUID,
        new_role: OrgRole,
    ) -> OrganizationMember:
        """Update a member's role (requires ORG_ADMIN). Prevents sole admin from self-demotion."""
        await self.verify_membership(org_id, actor_id, required_roles=[OrgRole.ORG_ADMIN])

        stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == target_user_id,
        )
        member = (await self.session.execute(stmt)).scalar_one_or_none()
        if member is None:
            raise NotOrganizationMemberException(org_id)

        # Invariant: Prevent sole admin from demoting themselves
        if actor_id == target_user_id and new_role != OrgRole.ORG_ADMIN:
            admin_count_stmt = select(func.count(OrganizationMember.id)).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.role == OrgRole.ORG_ADMIN.value,
                OrganizationMember.status == MembershipStatus.ACTIVE.value,
            )
            admin_count = (await self.session.execute(admin_count_stmt)).scalar_one()
            if admin_count <= 1:
                raise InsufficientPermissionException("Cannot demote the sole active administrator of an organization")

        old_role = member.role
        member.role = new_role.value
        await self.audit_service.log_event(
            organization_id=org_id,
            project_id=None,
            actor_id=str(actor_id),
            action_type="MEMBER_ROLE_UPDATED",
            affected_entity_type="OrganizationMember",
            affected_entity_id=str(member.id),
            execution_context={"target_user_id": str(target_user_id), "old_role": old_role, "new_role": new_role.value},
        )
        await self.session.commit()
        await self.session.refresh(member)
        return member

    async def update_member_status(
        self,
        org_id: uuid.UUID,
        actor_id: uuid.UUID,
        target_user_id: uuid.UUID,
        new_status: MembershipStatus,
    ) -> OrganizationMember:
        """Update member lifecycle status (P2-LIM-007). Requires ORG_ADMIN."""
        await self.verify_membership(org_id, actor_id, required_roles=[OrgRole.ORG_ADMIN])

        stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == target_user_id,
        )
        member = (await self.session.execute(stmt)).scalar_one_or_none()
        if member is None:
            raise NotOrganizationMemberException(org_id)

        # Invariant: Prevent suspending or revoking sole active admin
        if member.role == OrgRole.ORG_ADMIN.value and new_status != MembershipStatus.ACTIVE:
            admin_count_stmt = select(func.count(OrganizationMember.id)).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.role == OrgRole.ORG_ADMIN.value,
                OrganizationMember.status == MembershipStatus.ACTIVE.value,
            )
            admin_count = (await self.session.execute(admin_count_stmt)).scalar_one()
            if admin_count <= 1:
                raise InsufficientPermissionException("Cannot suspend or revoke the sole active administrator of an organization")

        old_status = member.status
        member.status = new_status.value
        # Note on P2-LIM-007: Do NOT terminate user sessions globally across other organizations.
        # Suspension is strictly organization-scoped: authoritative per-request checks
        # (verify_membership & get_active_tenant_context) immediately deny access to this organization
        # without disrupting active sessions or access in other organizations.

        await self.audit_service.log_event(
            organization_id=org_id,
            project_id=None,
            actor_id=str(actor_id),
            action_type="MEMBER_STATUS_UPDATED",
            affected_entity_type="OrganizationMember",
            affected_entity_id=str(member.id),
            execution_context={"target_user_id": str(target_user_id), "old_status": old_status, "new_status": new_status.value},
        )
        await self.session.commit()
        await self.session.refresh(member)
        return member

    async def remove_member(
        self,
        org_id: uuid.UUID,
        actor_id: uuid.UUID,
        target_user_id: uuid.UUID,
    ) -> None:
        """Remove organization membership and cascade cleanup of project memberships (P2-LIM-002)."""
        await self.verify_membership(org_id, actor_id, required_roles=[OrgRole.ORG_ADMIN])

        stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == target_user_id,
        )
        member = (await self.session.execute(stmt)).scalar_one_or_none()
        if member is None:
            raise NotOrganizationMemberException(org_id)

        # Invariant: Prevent removing sole admin
        if member.role == OrgRole.ORG_ADMIN.value:
            admin_count_stmt = select(func.count(OrganizationMember.id)).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.role == OrgRole.ORG_ADMIN.value,
                OrganizationMember.status == MembershipStatus.ACTIVE.value,
            )
            admin_count = (await self.session.execute(admin_count_stmt)).scalar_one()
            if admin_count <= 1:
                raise InsufficientPermissionException("Cannot remove the sole active administrator of an organization")

        # Explicitly delete project memberships for this tenant before member deletion (P2-LIM-002)
        await self.session.execute(
            delete(ProjectMember).where(
                ProjectMember.organization_id == org_id,
                ProjectMember.user_id == target_user_id,
            )
        )
        await self.audit_service.log_event(
            organization_id=org_id,
            project_id=None,
            actor_id=str(actor_id),
            action_type="MEMBER_REMOVED",
            affected_entity_type="OrganizationMember",
            affected_entity_id=str(member.id),
            execution_context={"target_user_id": str(target_user_id)},
        )
        await self.session.delete(member)
        await self.session.commit()

    # ==========================================================================
    # Project & Workspace Management (Tenant Isolated)
    # ==========================================================================

    async def create_project(
        self,
        org_id: uuid.UUID,
        actor_id: uuid.UUID,
        req: ProjectCreateRequest,
    ) -> Project:
        """Create a new project workspace strictly scoped to the active organization (P2-LIM-008, P2-LIM-009)."""
        org_member = await self.verify_membership(org_id, actor_id)

        # Invariant: Prevent auditors from acquiring project write authority (P2-LIM-009)
        if org_member.role == OrgRole.AUDITOR.value:
            raise InsufficientPermissionException(
                "Auditors hold read-only oversight privileges and are not permitted to create project workspaces"
            )

        slug = req.slug or slugify(req.name)
        base_slug = slug
        counter = 1
        while True:
            stmt = select(Project).where(
                Project.organization_id == org_id,
                Project.slug == slug,
            )
            if (await self.session.execute(stmt)).scalar_one_or_none() is None:
                break
            slug = f"{base_slug}-{counter}"
            counter += 1

        project = Project(
            id=uuid.uuid4(),
            organization_id=org_id,
            name=req.name,
            slug=slug,
            description=req.description,
            status=ProjectStatus.ACTIVE.value,
        )
        self.session.add(project)
        await self.session.flush()

        # Creator automatically becomes PROJECT_LEAD
        proj_member = ProjectMember(
            id=uuid.uuid4(),
            organization_id=org_id,
            project_id=project.id,
            user_id=actor_id,
            project_role=ProjectRole.PROJECT_LEAD.value,
        )
        self.session.add(proj_member)
        await self.audit_service.log_event(
            organization_id=org_id,
            project_id=project.id,
            actor_id=str(actor_id),
            action_type="PROJECT_CREATED",
            affected_entity_type="Project",
            affected_entity_id=str(project.id),
            execution_context={"name": project.name, "slug": slug},
        )
        try:
            await self.session.commit()
            await self.session.refresh(project)
            return project
        except IntegrityError as exc:
            await self.session.rollback()
            raise CorbelException(
                message=f"Project slug '{slug}' already exists in this organization. Please choose a different name or slug.",
                status_code=409,
                error_code="SLUG_CONFLICT",
            ) from exc

    async def list_projects(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Sequence[Project]:
        """List projects within the authorized organization respecting project membership (P2-LIM-005)."""
        org_member = await self.verify_membership(org_id, user_id)

        if org_member.role == OrgRole.ORG_ADMIN.value:
            stmt = (
                select(Project)
                .where(Project.organization_id == org_id)
                .order_by(Project.created_at.desc())
            )
        else:
            stmt = (
                select(Project)
                .join(
                    ProjectMember,
                    (ProjectMember.project_id == Project.id)
                    & (ProjectMember.organization_id == org_id),
                )
                .where(
                    Project.organization_id == org_id,
                    ProjectMember.user_id == user_id,
                )
                .order_by(Project.created_at.desc())
            )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_project(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Project:
        """Retrieve a project by ID, strictly enforcing organization ownership and project access (P2-LIM-005)."""
        await self.verify_project_access(org_id, project_id, user_id)

        stmt = select(Project).where(
            Project.organization_id == org_id,
            Project.id == project_id,
        )
        result = await self.session.execute(stmt)
        project = result.scalar_one_or_none()
        if project is None:
            raise ProjectNotFoundException(project_id)
        return project

    async def update_project(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        actor_id: uuid.UUID,
        req: ProjectUpdateRequest,
    ) -> Project:
        """Update project metadata within the active organization."""
        project = await self.get_project(org_id, project_id, actor_id)

        # Check project role or org admin
        await self.verify_project_access(org_id, project_id, actor_id, min_role=[ProjectRole.PROJECT_LEAD])

        if req.name is not None:
            project.name = req.name
        if req.description is not None:
            project.description = req.description
        if req.status is not None:
            project.status = req.status.value

        await self.audit_service.log_event(
            organization_id=org_id,
            project_id=project.id,
            actor_id=str(actor_id),
            action_type="PROJECT_UPDATED",
            affected_entity_type="Project",
            affected_entity_id=str(project.id),
            execution_context={"name": project.name, "status": project.status},
        )
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def delete_project(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        """Delete project workspace within authorized tenant."""
        project = await self.get_project(org_id, project_id, actor_id)
        await self.verify_project_access(org_id, project_id, actor_id, min_role=[ProjectRole.PROJECT_LEAD])

        await self.audit_service.log_event(
            organization_id=org_id,
            project_id=project.id,
            actor_id=str(actor_id),
            action_type="PROJECT_DELETED",
            affected_entity_type="Project",
            affected_entity_id=str(project.id),
        )
        await self.session.delete(project)
        await self.session.commit()

    # ==========================================================================
    # Project Membership & Cross-Tenant Defense
    # ==========================================================================

    async def verify_project_access(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        min_role: list[ProjectRole] | None = None,
    ) -> ProjectMember | None:
        """Verify project access or allow ORG_ADMIN fallback."""
        org_member = await self.verify_membership(org_id, user_id)
        if org_member.role == OrgRole.ORG_ADMIN.value:
            return None  # Org Admin has supervisory access

        stmt = select(ProjectMember).where(
            ProjectMember.organization_id == org_id,
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
        pm = (await self.session.execute(stmt)).scalar_one_or_none()
        if pm is None:
            raise InsufficientPermissionException("You are not an assigned member of this project")

        if min_role and pm.project_role not in [r.value for r in min_role]:
            raise InsufficientPermissionException(f"Project operation requires one of: {[r.value for r in min_role]}")

        return pm

    async def add_project_member(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        actor_id: uuid.UUID,
        target_user_id: uuid.UUID,
        role: ProjectRole,
    ) -> ProjectMember:
        """Assign a user to a project. Enforces that target user belongs to the SAME organization."""
        # 1. Verify project exists in this tenant
        await self.get_project(org_id, project_id, actor_id)
        # 2. Verify actor has permissions
        await self.verify_project_access(org_id, project_id, actor_id, min_role=[ProjectRole.PROJECT_LEAD])

        # 3. CRITICAL INVARIANT: Verify target user belongs to the SAME organization
        target_membership_stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == target_user_id,
            OrganizationMember.status == MembershipStatus.ACTIVE.value,
        )
        target_org_member = (await self.session.execute(target_membership_stmt)).scalar_one_or_none()
        if target_org_member is None:
            raise CrossTenantViolationException(
                "Cross-tenant assignment rejected: Target user is not an active member of this organization"
            )

        # 4. Check if already a project member
        stmt = select(ProjectMember).where(
            ProjectMember.organization_id == org_id,
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == target_user_id,
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            old_role = existing.project_role
            existing.project_role = role.value
            await self.audit_service.log_event(
                organization_id=org_id,
                project_id=project_id,
                actor_id=str(actor_id),
                action_type="PROJECT_MEMBER_UPDATED",
                affected_entity_type="ProjectMember",
                affected_entity_id=str(existing.id),
                execution_context={
                    "target_user_id": str(target_user_id),
                    "previous_role": old_role,
                    "new_role": role.value,
                    "operation_type": "UPDATE",
                },
            )
            try:
                await self.session.commit()
                await self.session.refresh(existing)
                return existing
            except Exception:
                await self.session.rollback()
                raise

        pm = ProjectMember(
            id=uuid.uuid4(),
            organization_id=org_id,
            project_id=project_id,
            user_id=target_user_id,
            project_role=role.value,
        )
        self.session.add(pm)
        await self.session.flush()
        await self.audit_service.log_event(
            organization_id=org_id,
            project_id=project_id,
            actor_id=str(actor_id),
            action_type="PROJECT_MEMBER_ADDED",
            affected_entity_type="ProjectMember",
            affected_entity_id=str(pm.id),
            execution_context={
                "target_user_id": str(target_user_id),
                "previous_role": None,
                "new_role": role.value,
                "operation_type": "ASSIGN",
            },
        )
        try:
            await self.session.commit()
            await self.session.refresh(pm)
            return pm
        except Exception:
            await self.session.rollback()
            raise

    async def list_project_members(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Sequence[tuple[ProjectMember, User]]:
        """List all members assigned to a project enforcing project access (P2-LIM-005)."""
        await self.verify_project_access(org_id, project_id, user_id)

        stmt = (
            select(ProjectMember, User)
            .join(User, User.id == ProjectMember.user_id)
            .where(
                ProjectMember.organization_id == org_id,
                ProjectMember.project_id == project_id,
            )
            .order_by(ProjectMember.granted_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.tuples().all()

    async def remove_project_member(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        actor_id: uuid.UUID,
        target_user_id: uuid.UUID,
    ) -> None:
        """Remove user from project membership."""
        await self.get_project(org_id, project_id, actor_id)
        await self.verify_project_access(org_id, project_id, actor_id, min_role=[ProjectRole.PROJECT_LEAD])

        stmt = select(ProjectMember).where(
            ProjectMember.organization_id == org_id,
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == target_user_id,
        )
        pm = (await self.session.execute(stmt)).scalar_one_or_none()
        if pm is not None:
            await self.audit_service.log_event(
                organization_id=org_id,
                project_id=project_id,
                actor_id=str(actor_id),
                action_type="PROJECT_MEMBER_REMOVED",
                affected_entity_type="ProjectMember",
                affected_entity_id=str(pm.id),
                execution_context={
                    "target_user_id": str(target_user_id),
                    "role": pm.project_role,
                    "operation_type": "REMOVE",
                },
            )
            await self.session.delete(pm)
            try:
                await self.session.commit()
            except Exception:
                await self.session.rollback()
                raise

    # ==========================================================================
    # Maintenance & Retention (P2-LIM-006)
    # ==========================================================================

    async def purge_expired_records(
        self,
        retention_days: int = 30,
        batch_size: int = 500,
        max_batches: int = 100,
    ) -> dict[str, int]:
        """Safely prune expired or revoked refresh tokens, sessions, and rate limit buckets outside retention window using bounded batches (P2-LIM-006)."""
        now_utc = datetime.now(UTC)
        cutoff = now_utc - timedelta(days=retention_days)

        # 1. Bounded batch purge of expired/revoked refresh tokens older than cutoff
        purged_tokens = 0
        for _ in range(max_batches):
            token_ids_stmt = (
                select(RefreshToken.id)
                .where(
                    (RefreshToken.expires_at < cutoff)
                    | (RefreshToken.is_revoked.is_(True) & (RefreshToken.revoked_at < cutoff))
                )
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
            batch_token_ids = (await self.session.execute(token_ids_stmt)).scalars().all()
            if not batch_token_ids:
                break

            await self.session.execute(
                delete(RefreshToken).where(RefreshToken.id.in_(batch_token_ids))
            )
            await self.session.commit()
            purged_tokens += len(batch_token_ids)

        # 2. Bounded batch purge of expired/revoked sessions older than cutoff
        purged_sessions = 0
        for _ in range(max_batches):
            session_ids_stmt = (
                select(UserSession.id)
                .where(
                    (UserSession.expires_at < cutoff)
                    | (
                        (UserSession.status.in_([SessionStatus.EXPIRED.value, SessionStatus.REVOKED.value]))
                        & (UserSession.created_at < cutoff)
                    )
                )
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
            batch_session_ids = (await self.session.execute(session_ids_stmt)).scalars().all()
            if not batch_session_ids:
                break

            await self.session.execute(
                delete(UserSession).where(UserSession.id.in_(batch_session_ids))
            )
            await self.session.commit()
            purged_sessions += len(batch_session_ids)

        # 3. Bounded batch purge of expired rate-limiting buckets older than cutoff
        purged_rate_limit_buckets = 0
        for _ in range(max_batches):
            bucket_keys_stmt = (
                select(RateLimitBucket.key)
                .where(
                    (RateLimitBucket.last_updated < cutoff)
                    & (
                        (RateLimitBucket.blocked_until.is_(None))
                        | (RateLimitBucket.blocked_until < now_utc)
                    )
                )
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
            batch_bucket_keys = (await self.session.execute(bucket_keys_stmt)).scalars().all()
            if not batch_bucket_keys:
                break

            await self.session.execute(
                delete(RateLimitBucket).where(RateLimitBucket.key.in_(batch_bucket_keys))
            )
            await self.session.commit()
            purged_rate_limit_buckets += len(batch_bucket_keys)

        return {
            "purged_refresh_tokens": purged_tokens,
            "purged_user_sessions": purged_sessions,
            "purged_rate_limit_buckets": purged_rate_limit_buckets,
        }
