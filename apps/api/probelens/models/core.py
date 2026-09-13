from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Computed,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from probelens.models.base import Base, TimestampMixin
from probelens.models.enums import Role


def enum_col(enum_cls, **kw):
    return Enum(enum_cls, native_enum=False, length=32, values_callable=lambda e: [m.value for m in e], **kw)


def search_vector(*columns: str):
    """Persisted tsvector over the given text columns; every searchable table shares this shape."""
    expr = " || ' ' || ".join(f"coalesce({c}, '')" for c in columns)
    return mapped_column(TSVECTOR, Computed(f"to_tsvector('english', {expr})", persisted=True))


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(enum_col(Role), default=Role.viewer)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    team: Mapped[Team | None] = relationship()


class Product(Base):
    """Catalog dimension. Stock and velocity feed the inventory-risk view."""

    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(40), index=True)
    subcategory: Mapped[str] = mapped_column(String(60))
    price: Mapped[float] = mapped_column(Float)
    stock_units: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Stakeholder(Base):
    __tablename__ = "stakeholders"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255))
    team: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(120))


class Comment(Base, TimestampMixin):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[int] = mapped_column(Integer)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)

    author: Mapped[User] = relationship()

    __table_args__ = (Index("ix_comments_entity", "entity_type", "entity_id"),)


class SavedAnalysis(Base, TimestampMixin):
    __tablename__ = "saved_analyses"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(20))  # analysis | funnel | cohort
    config: Mapped[dict] = mapped_column(JSONB)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    owner: Mapped[User] = relationship()
    search_vector = search_vector("name", "description")

    __table_args__ = (Index("ix_saved_analyses_search", "search_vector", postgresql_using="gin"),)


class Segment(Base, TimestampMixin):
    __tablename__ = "segments"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    conditions: Mapped[list] = mapped_column(JSONB)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    owner: Mapped[User] = relationship()


class Anomaly(Base, TimestampMixin):
    __tablename__ = "anomalies"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    metric_key: Mapped[str] = mapped_column(String(60), index=True)
    filters: Mapped[list] = mapped_column(JSONB, default=list)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    expected: Mapped[float] = mapped_column(Float)
    actual: Mapped[float] = mapped_column(Float)
    baseline_std: Mapped[float] = mapped_column(Float)
    zscore: Mapped[float] = mapped_column(Float)
    direction: Mapped[str] = mapped_column(String(8))  # up | down
    severity: Mapped[str] = mapped_column(String(8))  # low | medium | high
    status: Mapped[str] = mapped_column(String(20), default="open")
    investigation_id: Mapped[int | None] = mapped_column(ForeignKey("investigations.id"))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_anomalies_unique_window", "metric_key", "period_end", "filters", unique=True),
    )
