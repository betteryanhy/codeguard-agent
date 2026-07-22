from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.services.storage import StorageService, UserRecord
from app.services.auth_service import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
security = HTTPBearer()
storage = StorageService()


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserRecord:
    """Dependency: get current authenticated user from JWT token."""
    token = credentials.credentials
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = await storage.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
) -> Optional[UserRecord]:
    """Optional auth dependency - returns None if no valid token."""
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """Authenticate user and return JWT token."""
    user = await storage.get_user_by_username(req.username)
    if user is None or not verify_password(req.password, user.password_hash):
        await log_action(
            action="login_failed",
            resource_type="auth",
            user=req.username,
        )
        raise HTTPException(status_code=401, detail="Invalid username or password")

    access_token = create_access_token({"sub": user.id, "username": user.username, "role": user.role})

    await log_action(
        action="login",
        resource_type="auth",
        resource_id=user.id,
        user=user.username,
    )

    return LoginResponse(
        access_token=access_token,
        user={
            "id": user.id,
            "username": user.username,
            "role": user.role,
        },
    )


@router.post("/refresh")
async def refresh(current_user: UserRecord = Depends(get_current_user)):
    """Refresh JWT token."""
    new_token = create_access_token({
        "sub": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
    })
    return {"access_token": new_token, "token_type": "bearer"}


@router.get("/me")
async def me(current_user: UserRecord = Depends(get_current_user)):
    """Get current user info."""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
    }


@router.put("/password")
async def change_password(
    req: ChangePasswordRequest,
    current_user: UserRecord = Depends(get_current_user),
):
    """Change current user's password."""
    if not verify_password(req.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Old password is incorrect")

    current_user.password_hash = hash_password(req.new_password)
    await storage.save_user(current_user)

    await log_action(
        action="password_changed",
        resource_type="auth",
        resource_id=current_user.id,
        user=current_user.username,
    )

    return {"message": "Password updated successfully"}
