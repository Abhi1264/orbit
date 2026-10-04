from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from probelens.experiments.analysis import analyze, reference_readouts
from probelens.experiments.spec import spec_from_model
from probelens.models import Experiment, ExperimentSnapshot
from probelens.models.enums import ExperimentStatus

REFERENCE_METRICS = ["conversion", "revenue"]


def snapshot_experiments(db: Session, as_of: date) -> int:
    experiments = db.scalars(
        select(Experiment)
        .options(selectinload(Experiment.variants))
        .where(Experiment.status != ExperimentStatus.draft)
    ).all()
    computed_at = datetime.now(UTC)
    for exp in experiments:
        spec = spec_from_model(exp)
        designed = {spec.primary_metric, *spec.guardrail_metrics}
        reference = reference_readouts(spec, as_of, [k for k in REFERENCE_METRICS if k not in designed])
        db.merge(
            ExperimentSnapshot(
                experiment_id=exp.id,
                as_of=as_of,
                computed_at=computed_at,
                results=analyze(spec, as_of).model_dump(mode="json"),
                reference_metrics=[r.model_dump(mode="json") for r in reference],
            )
        )
    return len(experiments)
