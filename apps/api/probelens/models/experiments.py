from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from probelens.models.base import Base, TimestampMixin
from probelens.models.core import User, enum_col, search_vector
from probelens.models.enums import ExperimentDecision, ExperimentStatus

class Experiment(Base, TimestampMixin):
    __tablename__ = "experiments"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    key: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    hypothesis: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[ExperimentStatus] = mapped_column(
        enum_col(ExperimentStatus), default=ExperimentStatus.draft
    )
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    primary_metric: Mapped[str] = mapped_column(String(60))
    guardrail_metrics: Mapped[list] = mapped_column(JSONB, default=list)
    audience_filters: Mapped[list] = mapped_column(JSONB, default=list)
    traffic_percent: Mapped[int] = mapped_column(Integer, default=100)
    min_sample_per_variant: Mapped[int] = mapped_column(Integer, default=2000)
    min_relative_effect: Mapped[float] = mapped_column(Float, default=0.02)
    min_duration_days: Mapped[int] = mapped_column(Integer, default=7)
    # True when the seed baked exposure records into the event stream. App-created
    # experiments are analysed on hash-based retroactive assignment instead.
    has_exposure_events: Mapped[bool] = mapped_column(Boolean, default=False)
    decision: Mapped[ExperimentDecision | None] = mapped_column(enum_col(ExperimentDecision))
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    owner: Mapped[User] = relationship(foreign_keys=[owner_id])
    decided_by: Mapped[User | None] = relationship(foreign_keys=[decided_by_id])
    variants: Mapped[list["ExperimentVariant"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan", order_by="ExperimentVariant.id"
    )
    search_vector = search_vector("name", "hypothesis", "description")

    __table_args__ = (Index("ix_experiments_search", "search_vector", postgresql_using="gin"),)

class ExperimentVariant(Base):
    __tablename__ = "experiment_variants"
    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    weight: Mapped[int] = mapped_column(Integer, default=50)
    is_control: Mapped[bool] = mapped_column(Boolean, default=False)

    experiment: Mapped[Experiment] = relationship(back_populates="variants")
