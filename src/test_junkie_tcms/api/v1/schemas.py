from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["viewer", "tester", "editor", "admin", "owner"]


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


T = TypeVar("T")


class Page(BaseModel, Generic[T]):  # noqa: UP046 - PEP 695 needs 3.12; we support 3.11
    items: list[T]
    next_cursor: str | None = None


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1000)


class MeOrg(BaseModel):
    slug: str
    name: str
    role: str


class MeOut(BaseModel):
    via: str
    user_id: str | None = None
    email: str | None = None
    name: str | None = None
    actor_id: str | None = None
    token_id: str | None = None
    orgs: list[MeOrg] = []


class OrgOut(Out):
    id: str
    slug: str
    name: str
    created_at: datetime


class OrgUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class MemberOut(BaseModel):
    user_id: str
    actor_id: str
    email: str
    name: str
    role: str
    removed_at: datetime | None = None


class MemberAdd(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    name: str = Field(min_length=1, max_length=200)
    role: Role
    # Only used when the email has no account yet.
    password: str | None = Field(None, min_length=8, max_length=1000)


class MemberUpdate(BaseModel):
    role: Role


class AgentOut(Out):
    id: str
    name: str
    role: str
    owner_user_id: str
    disabled_at: datetime | None = None
    created_at: datetime


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: Role
    # Defaults to the calling user.
    owner_user_id: str | None = None


class AgentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    role: Role | None = None


class TokenOut(Out):
    id: str
    name: str
    prefix: str
    actor_id: str
    scopes: list[str]
    product_ids: list[str] | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scopes: list[str] = Field(min_length=1)
    # Defaults to the caller's own actor.
    actor_id: str | None = None
    expires_at: datetime | None = None
    # Product restriction arrives in T2; T1 refuses a value.
    product_ids: list[str] | None = None


class TokenCreated(TokenOut):
    token: str = Field(description="Shown once; store it now")


class AuditOut(Out):
    id: str
    created_at: datetime
    actor_id: str
    token_id: str | None
    on_behalf_of_user_id: str | None
    via: str
    action: str
    entity_type: str
    entity_id: str
    changes: dict[str, Any] | None
