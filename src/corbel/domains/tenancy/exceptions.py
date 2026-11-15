"""Tenancy and authorization domain exceptions."""

from typing import Any

from corbel.core.exceptions import CorbelException


class UserAlreadyExistsException(CorbelException):
    def __init__(self, email: str) -> None:
        super().__init__(
            message=f"User with email '{email}' already exists",
            error_code="USER_ALREADY_EXISTS",
            status_code=409,
        )


class InvalidCredentialsException(CorbelException):
    def __init__(self, message: str = "Invalid email or password") -> None:
        super().__init__(
            message=message,
            error_code="INVALID_CREDENTIALS",
            status_code=401,
        )


class OrganizationNotFoundException(CorbelException):
    def __init__(self, org_id: Any = None) -> None:
        super().__init__(
            message="Organization not found",
            error_code="ORGANIZATION_NOT_FOUND",
            status_code=404,
            details={"organization_id": str(org_id)} if org_id else None,
        )


class ProjectNotFoundException(CorbelException):
    def __init__(self, project_id: Any = None) -> None:
        super().__init__(
            message="Project workspace not found",
            error_code="PROJECT_NOT_FOUND",
            status_code=404,
            details={"project_id": str(project_id)} if project_id else None,
        )


class NotOrganizationMemberException(CorbelException):
    def __init__(self, org_id: Any = None) -> None:
        super().__init__(
            message="You do not have active membership in this organization",
            error_code="NOT_ORGANIZATION_MEMBER",
            status_code=403,
            details={"organization_id": str(org_id)} if org_id else None,
        )


class OrganizationSuspendedException(CorbelException):
    def __init__(self, org_id: Any = None) -> None:
        super().__init__(
            message="This organization is currently suspended",
            error_code="ORGANIZATION_SUSPENDED",
            status_code=403,
            details={"organization_id": str(org_id)} if org_id else None,
        )


class MembershipInactiveException(CorbelException):
    def __init__(self, status: str) -> None:
        super().__init__(
            message=f"Your organization membership is {status.lower()}",
            error_code="MEMBERSHIP_INACTIVE",
            status_code=403,
            details={"membership_status": status},
        )


class InsufficientPermissionException(CorbelException):
    def __init__(self, required_role: str = "ORG_ADMIN") -> None:
        super().__init__(
            message=f"Operation requires {required_role} privileges",
            error_code="INSUFFICIENT_PERMISSIONS",
            status_code=403,
        )


class CrossTenantViolationException(CorbelException):
    def __init__(self, message: str = "Cross-tenant access or relationship violation detected") -> None:
        super().__init__(
            message=message,
            error_code="CROSS_TENANT_VIOLATION",
            status_code=403,
        )
