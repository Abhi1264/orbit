from fastapi import APIRouter, Response
from sqlalchemy import select

from probelens.api.deps import CurrentUser, DbSession
from probelens.config import get_settings
from probelens.core.errors import Unauthorized
from probelens.core.permissions import ROLE_PERMISSIONS
from probelens.core.security import SESSION_COOKIE, create_session_token, verify_password
from probelens.models import User
from probelens.schemas.auth import LoginRequest, UserOut, UserSummary

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        permissions=sorted(ROLE_PERMISSIONS[user.role]),
    )


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, db: DbSession) -> UserOut:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise Unauthorized("Invalid email or password")
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(user.id),
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    return _user_out(user)


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return _user_out(user)


@router.get("/users", response_model=list[UserSummary])
def list_users(_: CurrentUser, db: DbSession) -> list[User]:
    return list(db.scalars(select(User).where(User.is_active).order_by(User.name)))
