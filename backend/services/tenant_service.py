"""
Tenant and User Management Service.

Handles:
1. Organization (Tenant) Registration & First-Owner Onboarding.
2. User Authentication & Password Verification.
3. Tenant Memberships and RBAC Validation.
4. Domain Verification.
"""

from datetime import datetime, timezone
import uuid
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.tenant import (
    Tenant,
    TenantMembership,
    User,
    VerifiedDomain,
)
from services.crypto_service import hash_password, verify_password

VALID_ROLES = {"OWNER", "ADMIN", "EXECUTIVE", "ANALYST"}
ROLE_HIERARCHY = {
    "OWNER": 4,
    "ADMIN": 3,
    "EXECUTIVE": 2,
    "ANALYST": 1,
}


class TenantServiceError(Exception):
    """Base exception for tenant service errors."""
    pass


class AuthenticationError(TenantServiceError):
    """Raised on invalid login credentials."""
    pass


class AuthorizationError(TenantServiceError):
    """Raised when user lacks required role/membership in tenant."""
    pass


async def register_tenant_with_owner(
    name: str,
    slug: str,
    owner_email: str,
    owner_password: str,
    owner_full_name: str,
    session: AsyncSession,
) -> tuple[Tenant, User, TenantMembership]:
    """
    Controlled first-owner onboarding process:
    Creates a new Tenant and assigns the registrant as OWNER.
    """
    clean_slug = slug.strip().lower()
    clean_email = owner_email.strip().lower()

    # Check slug availability
    existing_slug = await session.execute(select(Tenant).where(Tenant.slug == clean_slug))
    if existing_slug.scalar_one_or_none():
        raise TenantServiceError(f"Tenant slug '{clean_slug}' is already registered")

    # Get or create user
    existing_user_stmt = select(User).where(User.email == clean_email)
    user_res = await session.execute(existing_user_stmt)
    user = user_res.scalar_one_or_none()

    if not user:
        user = User(
            user_id=uuid.uuid4(),
            email=clean_email,
            hashed_password=hash_password(owner_password),
            full_name=owner_full_name.strip(),
            is_active=True,
            is_superuser=False,
        )
        session.add(user)
        await session.flush()
    else:
        # Verify password if user already exists
        if not verify_password(owner_password, user.hashed_password):
            raise AuthenticationError("Invalid password for existing user account")

    # Create Tenant
    tenant = Tenant(
        tenant_id=uuid.uuid4(),
        slug=clean_slug,
        name=name.strip(),
        subscription_plan="standard",
        status="active",
        currency_code="INR",
    )
    session.add(tenant)
    await session.flush()

    # Create Owner Membership
    membership = TenantMembership(
        membership_id=uuid.uuid4(),
        tenant_id=tenant.tenant_id,
        user_id=user.user_id,
        role="OWNER",
        is_active=True,
    )
    session.add(membership)
    await session.flush()

    return tenant, user, membership


async def add_tenant_member(
    tenant_id: uuid.UUID,
    email: str,
    password: str,
    full_name: str,
    role: str,
    session: AsyncSession,
) -> tuple[User, TenantMembership]:
    """Add a new or existing user to a tenant with a designated role."""
    clean_role = role.upper()
    if clean_role not in VALID_ROLES:
        raise TenantServiceError(f"Invalid role '{role}'. Must be one of {sorted(VALID_ROLES)}")

    clean_email = email.strip().lower()

    # Check if membership already exists
    mem_check = await session.execute(
        select(TenantMembership)
        .join(User, TenantMembership.user_id == User.user_id)
        .where(TenantMembership.tenant_id == tenant_id, User.email == clean_email)
    )
    if mem_check.scalar_one_or_none():
        raise TenantServiceError(f"User '{clean_email}' already has a membership in this tenant")

    # Get or create user
    user_res = await session.execute(select(User).where(User.email == clean_email))
    user = user_res.scalar_one_or_none()

    if not user:
        user = User(
            user_id=uuid.uuid4(),
            email=clean_email,
            hashed_password=hash_password(password),
            full_name=full_name.strip(),
            is_active=True,
        )
        session.add(user)
        await session.flush()

    membership = TenantMembership(
        membership_id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user.user_id,
        role=clean_role,
        is_active=True,
    )
    session.add(membership)
    await session.flush()

    return user, membership


async def authenticate_user(
    email: str,
    password: str,
    session: AsyncSession,
) -> tuple[User, Sequence[TenantMembership]]:
    """Authenticate user credentials and retrieve their active tenant memberships."""
    clean_email = email.strip().lower()
    res = await session.execute(select(User).where(User.email == clean_email))
    user = res.scalar_one_or_none()

    if not user or not verify_password(password, user.hashed_password):
        raise AuthenticationError("Invalid email or password")
    if not user.is_active:
        raise AuthenticationError("User account is inactive")

    from db.session import set_session_user_context
    await set_session_user_context(session, user.user_id)

    mems_res = await session.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == user.user_id,
            TenantMembership.is_active == True,
        )
    )
    memberships = mems_res.scalars().all()
    return user, memberships


async def verify_membership_and_role(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    minimum_role: str | None,
    session: AsyncSession,
) -> TenantMembership:
    """Verify user belongs to tenant and meets role requirements."""
    res = await session.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.is_active == True,
        )
    )
    membership = res.scalar_one_or_none()
    if not membership:
        raise AuthorizationError(f"User {user_id} does not have an active membership in tenant {tenant_id}")

    if minimum_role:
        user_level = ROLE_HIERARCHY.get(membership.role.upper(), 0)
        required_level = ROLE_HIERARCHY.get(minimum_role.upper(), 99)
        if user_level < required_level:
            raise AuthorizationError(
                f"Role '{membership.role}' insufficient. Minimum role required: '{minimum_role}'"
            )

    return membership


async def require_tenant_role(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    allowed_roles: list[str] | str,
    session: AsyncSession,
) -> bool:
    """Check if user has one of the allowed roles (or higher in hierarchy) in tenant."""
    try:
        if isinstance(allowed_roles, str):
            allowed_roles = [allowed_roles]
        mem = await verify_membership_and_role(
            user_id=user_id,
            tenant_id=tenant_id,
            minimum_role=None,
            session=session,
        )
        if mem.role in allowed_roles:
            return True
        user_level = ROLE_HIERARCHY.get(mem.role.upper(), 0)
        min_allowed_level = min(ROLE_HIERARCHY.get(r.upper(), 99) for r in allowed_roles)
        return user_level >= min_allowed_level
    except AuthorizationError:
        return False

