from enum import StrEnum


class Role(StrEnum):
    admin = "admin"
    pm = "pm"
    analyst = "analyst"
    viewer = "viewer"


class ExperimentStatus(StrEnum):
    draft = "draft"
    running = "running"
    completed = "completed"
    stopped = "stopped"


class ExperimentDecision(StrEnum):
    ship = "ship"
    iterate = "iterate"
    stop = "stop"
    continue_ = "continue"


class InvestigationStatus(StrEnum):
    open = "open"
    investigating = "investigating"
    validating = "validating"
    resolved = "resolved"
    closed = "closed"


class FindingKind(StrEnum):
    observation = "observation"
    evidence = "evidence"
    hypothesis = "hypothesis"
    recommendation = "recommendation"


class HypothesisState(StrEnum):
    proposed = "proposed"
    supported = "supported"
    refuted = "refuted"


class Confidence(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class ActionStatus(StrEnum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"


class AnomalyStatus(StrEnum):
    open = "open"
    acknowledged = "acknowledged"
    investigating = "investigating"
    resolved = "resolved"


class ReleaseStatus(StrEnum):
    planned = "planned"
    in_progress = "in_progress"
    rolling_out = "rolling_out"
    completed = "completed"
    rolled_back = "rolled_back"


class EntityType(StrEnum):
    investigation = "investigation"
    experiment = "experiment"
    release = "release"
    analysis = "analysis"
    decision = "decision"
    sop = "sop"
    knowledge = "knowledge"


class DecisionStatus(StrEnum):
    proposed = "proposed"
    decided = "decided"
    superseded = "superseded"


class ChecklistStatus(StrEnum):
    not_started = "not_started"
    in_progress = "in_progress"
    complete = "complete"
