from collections.abc import Callable
from typing import Annotated

import structlog
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from probelens.core.errors import Forbidden, Unauthorized
from probelens.core.permissions import Permission, has_permission
from probelens.core.security import SESSION_COOKIE, decode_session_token
from probelens.db.postgres import get_db
from probelens.models import User

DbSession = Annotated[Session, Depends(get_db)]

def get_current_user(request: Request, db: DbSession) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        auth = request.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    user_id = decode_session_token(token) if token else None
    if user_id is None:
        raise Unauthorized()
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Session is no longer valid")
    structlog.contextvars.bind_contextvars(user_id=user.id)
    return user

CurrentUser = Annotated[User, Depends(get_current_user)]

def require(permission: Permission) -> Callable[[User], User]:
    def dependency(user: CurrentUser) -> User:
        if not has_permission(user.role, permission):
            raise Forbidden(f"Requires permission '{permission.value}'")
        return user

    return dependency
