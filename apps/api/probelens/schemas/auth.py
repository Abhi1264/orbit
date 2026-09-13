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
