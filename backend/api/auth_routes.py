"""
Multi-Tenant Authentication and Organization Management Routes.
"""

import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.tenant import TenantMembership, User
from db.session import get_db_session, set_session_user_context
from services.crypto_service import create_access_token, decode_access_token
from services.tenant_service import (
    AuthenticationError,
    AuthorizationError,
    TenantServiceError,
    add_tenant_member,
    authenticate_user,
    register_tenant_with_owner,
)

auth_router = APIRouter(tags=["Authentication & Tenants"])


class RegisterTenantRequest(BaseModel):
    name: str
    slug: str
    owner_email: EmailStr
    owner_password: str
    owner_full_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_id: uuid.UUID | None = None


class AddMemberRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: str  # 'OWNER', 'ADMIN', 'EXECUTIVE', 'ANALYST'


@auth_router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register New Organization & First Owner",
)
async def register_organization(
    req: RegisterTenantRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Controlled first-owner onboarding process creating a new isolated tenant."""
    try:
        tenant, user, membership = await register_tenant_with_owner(
            name=req.name,
            slug=req.slug,
            owner_email=req.owner_email,
            owner_password=req.owner_password,
            owner_full_name=req.owner_full_name,
            session=session,
        )
        token = create_access_token(
            user_id=user.user_id,
            email=user.email,
            tenant_id=tenant.tenant_id,
            role=membership.role,
        )
        return {
            "message": "Tenant registered successfully",
            "access_token": token,
            "token_type": "bearer",
            "tenant": {
                "tenant_id": str(tenant.tenant_id),
                "name": tenant.name,
                "slug": tenant.slug,
            },
            "user": {
                "user_id": str(user.user_id),
                "email": user.email,
                "full_name": user.full_name,
                "role": membership.role,
            },
        }
    except TenantServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@auth_router.post(
    "/login",
    summary="User Login",
)
async def login(
    req: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Authenticate user credentials and return access token with tenant list."""
    try:
        user, memberships = await authenticate_user(
            email=req.email,
            password=req.password,
            session=session,
        )
        selected_tenant_id = req.tenant_id or (memberships[0].tenant_id if memberships else None)
        active_role = None
        for m in memberships:
            if m.tenant_id == selected_tenant_id:
                active_role = m.role
                break

        token = create_access_token(
            user_id=user.user_id,
            email=user.email,
            tenant_id=selected_tenant_id,
            role=active_role,
        )

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "user_id": str(user.user_id),
                "email": user.email,
                "full_name": user.full_name,
            },
            "active_tenant_id": str(selected_tenant_id) if selected_tenant_id else None,
            "active_role": active_role,
            "tenants": [
                {
                    "tenant_id": str(m.tenant_id),
                    "role": m.role,
                }
                for m in memberships
            ],
        }
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e


class SwitchTenantRequest(BaseModel):
    tenant_id: uuid.UUID


@auth_router.post(
    "/switch-tenant",
    summary="Switch Active Tenant",
)
async def switch_tenant(
    req: SwitchTenantRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Generate a new access token for another verified active tenant membership."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")
    token = auth_header.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    user_id = uuid.UUID(payload["sub"])

    await set_session_user_context(session, user_id)
    mem_res = await session.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == req.tenant_id,
            TenantMembership.is_active == True,
        )
    )
    membership = mem_res.scalar_one_or_none()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have an active membership in the requested tenant.",
        )

    new_token = create_access_token(
        user_id=user_id,
        email=payload["email"],
        tenant_id=req.tenant_id,
        role=membership.role,
    )
    return {
        "access_token": new_token,
        "token_type": "bearer",
        "active_tenant_id": str(req.tenant_id),
        "active_role": membership.role,
    }


@auth_router.get(
    "/memberships",
    summary="List My Authorized Tenants",
)
async def get_my_memberships(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """List all organizations in which the authenticated user has an active membership."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")
    token = auth_header.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    user_id = uuid.UUID(payload["sub"])

    await set_session_user_context(session, user_id)
    mem_res = await session.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.is_active == True,
        )
    )
    memberships = mem_res.scalars().all()
    return {
        "user_id": str(user_id),
        "memberships": [
            {
                "tenant_id": str(m.tenant_id),
                "role": m.role,
                "is_active": m.is_active,
            }
            for m in memberships
        ],
    }

