from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from probelens.models.base import Base, TimestampMixin
from probelens.models.core import Stakeholder, User, enum_col, search_vector
from probelens.models.enums import (
    ChecklistStatus,
    DecisionStatus,
    FeedbackSentiment,
    FeedbackSource,
    FeedbackStatus,
    ReleaseStatus,
)

class Release(Base, TimestampMixin):
    __tablename__ = "releases"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    version: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    platform: Mapped[str] = mapped_column(String(20))  # android | ios | web | all
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[ReleaseStatus] = mapped_column(enum_col(ReleaseStatus), default=ReleaseStatus.planned)
    release_date: Mapped[date] = mapped_column(Date)
    rollout_percent: Mapped[int] = mapped_column(Integer, default=0)
    affected_areas: Mapped[list] = mapped_column(JSONB, default=list)
    experiment_id: Mapped[int | None] = mapped_column(ForeignKey("experiments.id"))

    owner: Mapped[User] = relationship()
    timeline: Mapped[list["ReleaseEvent"]] = relationship(
        back_populates="release", cascade="all, delete-orphan", order_by="ReleaseEvent.occurred_at"
    )
    search_vector = search_vector("version", "name", "description")

    __table_args__ = (
        Index("ix_releases_search", "search_vector", postgresql_using="gin"),
        Index("ix_releases_version_platform", "version", "platform", unique=True),
    )

class ReleaseEvent(Base):
    __tablename__ = "release_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    release_id: Mapped[int] = mapped_column(ForeignKey("releases.id", ondelete="CASCADE"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(String(40))  # status_change | rollout | note | link
    note: Mapped[str] = mapped_column(Text, default="")
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    release: Mapped[Release] = relationship(back_populates="timeline")
    actor: Mapped[User | None] = relationship()

class Sop(Base, TimestampMixin):
    """A reusable standard operating procedure. Items are ordered checklist
    entries; running an SOP against a release creates a Checklist copy."""

    __tablename__ = "sops"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(60))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    items: Mapped[list] = mapped_column(JSONB, default=list)  # [{key, label, owner_role}]

    owner: Mapped[User] = relationship()
    search_vector = search_vector("title", "description", "category")

    __table_args__ = (Index("ix_sops_search", "search_vector", postgresql_using="gin"),)

class Checklist(Base, TimestampMixin):
    __tablename__ = "checklists"
    id: Mapped[int] = mapped_column(primary_key=True)
    sop_id: Mapped[int | None] = mapped_column(ForeignKey("sops.id"))
    release_id: Mapped[int | None] = mapped_column(ForeignKey("releases.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[ChecklistStatus] = mapped_column(
        enum_col(ChecklistStatus), default=ChecklistStatus.not_started
    )
    items: Mapped[list] = mapped_column(JSONB, default=list)  # [{key, label, done, owner_id, done_at}]

    owner: Mapped[User] = relationship()
    sop: Mapped[Sop | None] = relationship()

class KnowledgeDocument(Base, TimestampMixin):
    __tablename__ = "knowledge_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    author: Mapped[User] = relationship()
    search_vector = search_vector("title", "body")

    __table_args__ = (Index("ix_knowledge_search", "search_vector", postgresql_using="gin"),)

class Decision(Base, TimestampMixin):
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(200))
    context: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[str] = mapped_column(Text, default="")
    alternatives: Mapped[str] = mapped_column(Text, default="")
    decision: Mapped[str] = mapped_column(Text)
    expected_impact: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[DecisionStatus] = mapped_column(enum_col(DecisionStatus), default=DecisionStatus.decided)
    decided_on: Mapped[date] = mapped_column(Date)
    follow_up_date: Mapped[date | None] = mapped_column(Date)
    investigation_id: Mapped[int | None] = mapped_column(ForeignKey("investigations.id"))
    experiment_id: Mapped[int | None] = mapped_column(ForeignKey("experiments.id"))
    release_id: Mapped[int | None] = mapped_column(ForeignKey("releases.id"))

    owner: Mapped[User] = relationship()
    search_vector = search_vector("title", "context", "evidence", "decision")

    __table_args__ = (Index("ix_decisions_search", "search_vector", postgresql_using="gin"),)

class Feedback(Base, TimestampMixin):
    """Stakeholder and customer feedback intake. Each item carries a theme so the
    ops view can show which problems keep recurring, and an optional link to the
    investigation, experiment, release, or decision that answers it."""

    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    stakeholder_id: Mapped[int | None] = mapped_column(ForeignKey("stakeholders.id"))
    submitted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    source: Mapped[FeedbackSource] = mapped_column(enum_col(FeedbackSource))
    theme: Mapped[str] = mapped_column(String(60), index=True)
    body: Mapped[str] = mapped_column(Text)
    sentiment: Mapped[FeedbackSentiment] = mapped_column(
        enum_col(FeedbackSentiment), default=FeedbackSentiment.neutral
    )
    status: Mapped[FeedbackStatus] = mapped_column(enum_col(FeedbackStatus), default=FeedbackStatus.new)
    platform: Mapped[str | None] = mapped_column(String(20))
    received_on: Mapped[date] = mapped_column(Date)
    linked_entity_type: Mapped[str | None] = mapped_column(String(32))
    linked_entity_id: Mapped[int | None] = mapped_column(Integer)

    stakeholder: Mapped[Stakeholder | None] = relationship()
    submitted_by: Mapped[User] = relationship()
    search_vector = search_vector("theme", "body")

    __table_args__ = (Index("ix_feedback_search", "search_vector", postgresql_using="gin"),)

class AiRun(Base):
    """Audit record for every analyst invocation: what was asked, which tools ran,
    how long it took, and what came back. Secrets never enter this table."""

    __tablename__ = "ai_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    question: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(10))  # llm | demo
    model: Mapped[str] = mapped_column(String(80), default="")
    tool_calls: Mapped[list] = mapped_column(JSONB, default=list)
    response: Mapped[dict] = mapped_column(JSONB)
    latency_ms: Mapped[int] = mapped_column(Integer)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
