from pydantic import BaseModel, EmailStr

from probelens.core.permissions import Permission
from probelens.models.enums import Role


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


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
