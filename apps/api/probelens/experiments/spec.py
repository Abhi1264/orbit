from probelens.analytics.dimensions import Filter
from probelens.experiments.analysis import ExperimentSpec
from probelens.experiments.assignment import VariantSpec
from probelens.models import Experiment


def spec_from_model(exp: Experiment) -> ExperimentSpec:
    control = next((v.key for v in exp.variants if v.is_control), exp.variants[0].key)
    return ExperimentSpec(
        key=exp.key,
        variants=[VariantSpec(v.key, v.weight) for v in exp.variants],
        control_key=control,
        start=exp.start_date,
        end=exp.end_date,
        primary_metric=exp.primary_metric,
        guardrail_metrics=list(exp.guardrail_metrics or []),
        audience_filters=[Filter.model_validate(f) for f in exp.audience_filters or []],
        traffic_percent=exp.traffic_percent,
        has_exposure_events=exp.has_exposure_events,
        min_sample_per_variant=exp.min_sample_per_variant,
        min_relative_effect=exp.min_relative_effect,
        min_duration_days=exp.min_duration_days,
    )
