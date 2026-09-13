from datetime import datetime

from pydantic import BaseModel, Field

from probelens.core.permissions import Permission
from probelens.models.enums import Role

class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)

class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: Role
    permissions: list[Permission]

    model_config = {"from_attributes": True}

class UserSummary(BaseModel):
    id: int
    name: str
    email: str
    role: Role

    model_config = {"from_attributes": True}

class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)

class RolePermissions(BaseModel):
    role: Role
    permissions: list[Permission]

class UserAdminOut(BaseModel):
    id: int
    email: str
    name: str
    role: Role
    is_active: bool
    team: str | None
    created_at: datetime
    updated_at: datetime

class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=200)
    role: Role = Role.viewer

class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)
