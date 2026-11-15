"""TenancyService handling user registration, authentication, organizations, and projects."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.core.config import get_settings
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
    RefreshToken,
    SessionStatus,
    User,
    UserSession,
)
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
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)


class TenancyService:
    """Core domain service for user authentication, organizations, and tenant-scoped workspaces."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ==========================================================================
    # Authentication & User Management
    # ==========================================================================

    async def register_user(self, req: UserRegisterRequest) -> User:
        """Register a new user account with hashed password."""
        # Check if user already exists
        stmt = select(User).where(func.lower(User.email) == req.email.lower())
        result = await self.session.execute(stmt)
        if result.scalar_one_or_none() is not None:
            raise UserAlreadyExistsException(req.email)

        hashed = hash_password(req.password)
        user = User(
            id=uuid.uuid4(),
            email=req.email.lower(),
            hashed_password=hashed,
            full_name=req.full_name,
            is_active=True,
            is_superuser=False,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def authenticate_user(
        self,
        req: UserLoginRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenResponse:
        """Authenticate user credentials and return access and refresh JWT tokens with persistent session."""
        stmt = select(User).where(func.lower(User.email) == req.email.lower())
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None or not verify_password(req.password, user.hashed_password):
            raise InvalidCredentialsException("Invalid email or password")

        if not user.is_active:
            raise InvalidCredentialsException("User account is inactive. Please contact your administrator.")

        settings = get_settings()
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
        )
        self.session.add(db_token)
        await self.session.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        """Issue a new access token and rotated refresh token.

        Enforces Refresh Token Rotation (RTR) and single-use semantics via PostgreSQL
        row locking (SELECT ... WITH FOR UPDATE). If an already-consumed or revoked
        refresh token is reused, all descendant tokens in the family and the associated
        session are immediately revoked (replay attack detection) and 401 is returned.
        """
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

        # 1. Acquire exclusive row lock on RefreshToken to prevent concurrent reuse
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

        # 3. CHECK REUSE: Is this token already consumed/revoked?
        if token_record.is_revoked:
            # Replay attack detected! Invalidate the entire session and all family tokens.
            if session_record is not None:
                session_record.status = SessionStatus.REVOKED.value
                session_record.revoked_at = now_utc

            await self.session.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == token_record.family_id)
                .values(is_revoked=True, revoked_at=now_utc)
            )
            await self.session.commit()
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

        # 7. Valid single-use rotation:
        # Atomically consume old token
        new_token_id = uuid.uuid4()
        token_record.is_revoked = True
        token_record.revoked_at = now_utc
        token_record.replaced_by = new_token_id

        # Issue replacement refresh token
        new_refresh_str, _, _, _, new_expires_at = create_refresh_token(
            user_id=user.id,
            email=user.email,
            session_id=session_record.id,
            family_id=token_record.family_id,
            token_id=new_token_id,
        )

        child_record = RefreshToken(
            id=new_token_id,
            session_id=session_record.id,
            user_id=user.id,
            token_hash=hash_token(new_refresh_str),
            family_id=token_record.family_id,
            is_revoked=False,
            expires_at=new_expires_at,
        )
        self.session.add(child_record)

        # Issue replacement access token bound to the active session
        settings = get_settings()
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
        """Create a new organization and grant creator ORG_ADMIN membership."""
        slug = req.slug or slugify(req.name)
        # Ensure slug uniqueness
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
        await self.session.commit()
        await self.session.refresh(org)
        return org

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
        stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        membership = result.scalar_one_or_none()

        if membership is None:
            raise NotOrganizationMemberException(org_id)

        if membership.status != MembershipStatus.ACTIVE.value:
            raise MembershipInactiveException(membership.status)

        # Check org status as well
        org = await self.session.get(Organization, org_id)
        if org is None or org.status == OrgStatus.SUSPENDED.value:
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
        return result.all()

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
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        new_member = OrganizationMember(
            id=uuid.uuid4(),
            organization_id=org_id,
            user_id=target_user.id,
            role=req.role.value,
            status=MembershipStatus.ACTIVE.value,
        )
        self.session.add(new_member)
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

        member.role = new_role.value
        await self.session.commit()
        await self.session.refresh(member)
        return member

    async def remove_member(
        self,
        org_id: uuid.UUID,
        actor_id: uuid.UUID,
        target_user_id: uuid.UUID,
    ) -> None:
        """Remove or revoke an organization membership (requires ORG_ADMIN). Prevents sole admin removal."""
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
        """Create a new project workspace strictly scoped to the active organization."""
        await self.verify_membership(org_id, actor_id)

        slug = req.slug or slugify(req.name)
        # Ensure project slug uniqueness within the organization
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
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def list_projects(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Sequence[Project]:
        """List all projects within the authorized organization (Strict Tenant Isolation)."""
        await self.verify_membership(org_id, user_id)

        stmt = (
            select(Project)
            .where(Project.organization_id == org_id)
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
        """Retrieve a project by ID, strictly enforcing organization ownership."""
        await self.verify_membership(org_id, user_id)

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
            raise InsufficientPermissionException(f"Project operation requires one of: {min_role}")

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
            existing.project_role = role.value
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        pm = ProjectMember(
            id=uuid.uuid4(),
            organization_id=org_id,
            project_id=project_id,
            user_id=target_user_id,
            project_role=role.value,
        )
        self.session.add(pm)
        await self.session.commit()
        await self.session.refresh(pm)
        return pm

    async def list_project_members(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Sequence[tuple[ProjectMember, User]]:
        """List all members assigned to a project."""
        await self.get_project(org_id, project_id, user_id)

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
        return result.all()

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
            await self.session.delete(pm)
            await self.session.commit()
