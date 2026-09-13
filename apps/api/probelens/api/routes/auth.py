from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from probelens.api.deps import CurrentUser, DbSession, require
from probelens.config import get_settings
from probelens.core import ratelimit
from probelens.core.errors import BadRequest, Forbidden, NotFound, Unauthorized
from probelens.core.logging import get_logger
from probelens.core.permissions import ROLE_PERMISSIONS, Permission
from probelens.core.security import SESSION_COOKIE, create_session_token, hash_password, verify_password
from probelens.models import User
from probelens.models.enums import Role
from probelens.schemas.auth import (
    LoginRequest,
    PasswordChange,
    RolePermissions,
    UserAdminOut,
    UserCreate,
    UserOut,
    UserSummary,
    UserUpdate,
)

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger("auth")

LOGIN_LIMIT = 10  # attempts
LOGIN_WINDOW = 15 * 60  # seconds
_admin = Depends(require(Permission.manage_users))


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        permissions=sorted(ROLE_PERMISSIONS[user.role]),
    )


def _admin_out(user: User) -> UserAdminOut:
    return UserAdminOut(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        is_active=user.is_active,
        team=user.team.name if user.team else None,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else request.client.host if request.client else "unknown")[:64]


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, request: Request, response: Response, db: DbSession) -> UserOut:
    email = payload.email.lower().strip()
    key = f"login:{_client_ip(request)}:{email}"
    allowed, retry_in = ratelimit.hit(key, LOGIN_LIMIT, LOGIN_WINDOW)
    if not allowed:
        log.warning("login_rate_limited", email=email)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many sign-in attempts; try again later",
            headers={"Retry-After": str(retry_in)},
        )
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        log.info("login_failed", email=email)
        raise Unauthorized("Invalid email or password")
    ratelimit.reset(key)
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
    log.info("login_ok", user_id=user.id, role=user.role.value)
    return _user_out(user)


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return _user_out(user)


@router.post("/password", status_code=204)
def change_password(payload: PasswordChange, user: CurrentUser, db: DbSession) -> None:
    if not verify_password(payload.current_password, user.password_hash):
        raise BadRequest("Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    db.flush()
    log.info("password_changed", user_id=user.id)


@router.get("/roles", response_model=list[RolePermissions])
def roles(_: CurrentUser) -> list[RolePermissions]:
    return [RolePermissions(role=r, permissions=sorted(p)) for r, p in ROLE_PERMISSIONS.items()]


@router.get("/users", response_model=list[UserSummary])
def list_users(_: CurrentUser, db: DbSession) -> list[User]:
    return list(db.scalars(select(User).where(User.is_active).order_by(User.name)))


@router.get("/admin/users", response_model=list[UserAdminOut], dependencies=[_admin])
def admin_list_users(
    _: CurrentUser, db: DbSession, include_inactive: bool = Query(default=True)
) -> list[UserAdminOut]:
    stmt = select(User).order_by(User.is_active.desc(), User.name)
    if not include_inactive:
        stmt = stmt.where(User.is_active)
    return [_admin_out(u) for u in db.scalars(stmt).all()]


@router.post("/admin/users", response_model=UserAdminOut, status_code=201, dependencies=[_admin])
def admin_create_user(payload: UserCreate, actor: CurrentUser, db: DbSession) -> UserAdminOut:
    email = payload.email.lower().strip()
    if db.scalar(select(User.id).where(User.email == email)):
        raise BadRequest("A user with this email already exists")
    user = User(
        email=email,
        name=payload.name.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        team_id=actor.team_id,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.refresh(user)
    log.info("user_created", user_id=user.id, role=user.role.value, by=actor.id)
    return _admin_out(user)


@router.patch("/admin/users/{user_id}", response_model=UserAdminOut, dependencies=[_admin])
def admin_update_user(user_id: int, payload: UserUpdate, actor: CurrentUser, db: DbSession) -> UserAdminOut:
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("User", user_id)
    data = payload.model_dump(exclude_unset=True)
    if user.id == actor.id:
        if data.get("is_active") is False:
            raise Forbidden("You cannot deactivate your own account")
        if "role" in data and data["role"] != Role.admin:
            raise Forbidden("You cannot remove your own admin role")
    if "role" in data and user.role == Role.admin and data["role"] != Role.admin:
        admins = db.scalar(select(User.id).where(User.role == Role.admin, User.is_active, User.id != user.id))
        if admins is None:
            raise BadRequest("At least one active admin is required")
    if data.get("password"):
        user.password_hash = hash_password(data.pop("password"))
    else:
        data.pop("password", None)
    for k, v in data.items():
        setattr(user, k, v)
    db.flush()
    db.refresh(user)
    log.info("user_updated", user_id=user.id, fields=sorted(data), by=actor.id)
    return _admin_out(user)


@router.delete("/admin/users/{user_id}", status_code=204, dependencies=[_admin])
def admin_delete_user(user_id: int, actor: CurrentUser, db: DbSession) -> None:
    """Hard delete for accounts that never touched anything; otherwise deactivate to keep the audit trail."""
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("User", user_id)
    if user.id == actor.id:
        raise Forbidden("You cannot delete your own account")
    try:
        with db.begin_nested():
            db.delete(user)
            db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This user owns records (investigations, comments, decisions…). Deactivate the account instead.",
        ) from exc
    log.info("user_deleted", user_id=user_id, by=actor.id)
