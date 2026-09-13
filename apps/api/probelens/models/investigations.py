from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from probelens.models.base import Base, TimestampMixin
from probelens.models.core import Stakeholder, User, enum_col, search_vector
from probelens.models.enums import (
    ActionStatus,
    Confidence,
    FindingKind,
    HypothesisState,
    InvestigationStatus,
)


class Investigation(Base, TimestampMixin):
    __tablename__ = "investigations"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[InvestigationStatus] = mapped_column(
        enum_col(InvestigationStatus), default=InvestigationStatus.open
    )
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    metric_key: Mapped[str] = mapped_column(String(60))
    filters: Mapped[list] = mapped_column(JSONB, default=list)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    baseline_start: Mapped[date] = mapped_column(Date)
    baseline_end: Mapped[date] = mapped_column(Date)
    observation: Mapped[str] = mapped_column(Text, default="")
    decision: Mapped[str] = mapped_column(Text, default="")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    release_id: Mapped[int | None] = mapped_column(ForeignKey("releases.id"), index=True)
    experiment_id: Mapped[int | None] = mapped_column(ForeignKey("experiments.id"), index=True)

    owner: Mapped[User] = relationship()
    findings: Mapped[list["InvestigationFinding"]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan", order_by="InvestigationFinding.id"
    )
    actions: Mapped[list["InvestigationAction"]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan", order_by="InvestigationAction.id"
    )
    stakeholders: Mapped[list["InvestigationStakeholder"]] = relationship(
        cascade="all, delete-orphan"
    )
    search_vector = search_vector("title", "observation", "decision")

    __table_args__ = (Index("ix_investigations_search", "search_vector", postgresql_using="gin"),)


class InvestigationFinding(Base, TimestampMixin):
    """A single entry in the evidence trail. `kind` keeps observed facts,
    hypotheses and recommendations visibly separate; `data` snapshots the query
    and numbers that back an evidence entry so the trail stays reproducible."""

    __tablename__ = "investigation_findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"))
    kind: Mapped[FindingKind] = mapped_column(enum_col(FindingKind))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[Confidence | None] = mapped_column(enum_col(Confidence))
    state: Mapped[HypothesisState | None] = mapped_column(enum_col(HypothesisState))
    data: Mapped[dict | None] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(20), default="user")  # user | analyst | system
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    investigation: Mapped[Investigation] = relationship(back_populates="findings")
    author: Mapped[User | None] = relationship()


class InvestigationAction(Base, TimestampMixin):
    __tablename__ = "investigation_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[ActionStatus] = mapped_column(enum_col(ActionStatus), default=ActionStatus.todo)
    due_date: Mapped[date | None] = mapped_column(Date)

    investigation: Mapped[Investigation] = relationship(back_populates="actions")
    owner: Mapped[User | None] = relationship()


class InvestigationStakeholder(Base):
    __tablename__ = "investigation_stakeholders"
    investigation_id: Mapped[int] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), primary_key=True
    )
    stakeholder_id: Mapped[int] = mapped_column(ForeignKey("stakeholders.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(60), default="informed")
    sort: Mapped[int] = mapped_column(Integer, default=0)

    stakeholder: Mapped[Stakeholder] = relationship()
