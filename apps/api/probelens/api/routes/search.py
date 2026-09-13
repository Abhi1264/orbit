"""Global search across every object with a search vector, plus metrics and dimensions.

Each searchable table exposes a persisted tsvector (see models.core.search_vector), so one
ranked query per table is cheap. Results are grouped by type; the client decides layout.
"""

from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from probelens.analytics.dimensions import DIMENSIONS
from probelens.analytics.metrics import METRICS
from probelens.api.deps import CurrentUser, DbSession, require
from probelens.core.permissions import Permission
from probelens.models import (
    Decision,
    Experiment,
    Feedback,
    Investigation,
    KnowledgeDocument,
    Release,
    SavedAnalysis,
    Sop,
)
from probelens.schemas.ops import SearchHit, SearchResponse

router = APIRouter(tags=["search"], dependencies=[Depends(require(Permission.view))])

@dataclass(frozen=True)
class _Source:
    type: str
    model: Any
    title: Any
    subtitle: Any
    status: Any = None
    extra: tuple[str, ...] = ()

_SOURCES = [
    _Source(
        "investigation", Investigation, Investigation.title, Investigation.observation, Investigation.status
    ),
    _Source("experiment", Experiment, Experiment.name, Experiment.hypothesis, Experiment.status, ("key",)),
    _Source("release", Release, Release.name, Release.description, Release.status, ("version", "platform")),
    _Source("decision", Decision, Decision.title, Decision.decision, Decision.status),
    _Source("sop", Sop, Sop.title, Sop.description, None, ("category",)),
    _Source("knowledge", KnowledgeDocument, KnowledgeDocument.title, KnowledgeDocument.body),
    _Source("feedback", Feedback, Feedback.theme, Feedback.body, Feedback.status, ("source", "sentiment")),
    _Source("saved", SavedAnalysis, SavedAnalysis.name, SavedAnalysis.description, None, ("kind",)),
]

def _or_terms(q: str) -> str:
    words = [w for w in "".join(ch if ch.isalnum() else " " for ch in q).split() if len(w) > 1]
    return " | ".join(words)

def _search_table(db: Session, src: _Source, q: str, limit: int) -> list[SearchHit]:
    m = src.model
    vec = m.search_vector

    def run(ts):
        rank = func.ts_rank(vec, ts).label("rank")
        stmt = select(m, rank).where(vec.op("@@")(ts)).order_by(rank.desc(), m.updated_at.desc()).limit(limit)
        return db.execute(stmt).all()

    rows = run(func.plainto_tsquery("english", q))
    if not rows and len(q.split()) > 1 and (terms := _or_terms(q)):
        rows = run(func.to_tsquery("english", terms))
    if not rows and len(q) >= 3:
        # Prefix/substring fallback so partial words (e.g. "8.4") still find the release.
        like = f"%{q}%"
        stmt = (
            select(m)
            .where(or_(src.title.ilike(like), src.subtitle.ilike(like)))
            .order_by(m.updated_at.desc())
            .limit(limit)
        )
        rows = [(obj, 0.01) for obj in db.scalars(stmt).all()]

    hits: list[SearchHit] = []
    for obj, rank in rows:
        subtitle = str(getattr(obj, src.subtitle.key) or "")
        subtitle = " ".join(w for w in subtitle.split() if not w.startswith("#"))
        if len(subtitle) > 140:
            subtitle = subtitle[:139].rsplit(" ", 1)[0] + "…"
        status = getattr(obj, src.status.key) if src.status is not None else None
        hits.append(
            SearchHit(
                type=src.type,
                id=obj.id,
                title=str(getattr(obj, src.title.key)),
                subtitle=subtitle,
                status=str(status) if status is not None else None,
                rank=float(rank),
                updated_at=getattr(obj, "updated_at", None),
                extra={k: getattr(obj, k) for k in src.extra},
            )
        )
    return hits

def _search_catalog(q: str) -> list[SearchHit]:
    """Metrics and dimensions are code, not rows; match on label/key/description."""
    needle = q.lower()
    hits: list[SearchHit] = []
    for m in METRICS.values():
        hay = f"{m.key} {m.label} {m.description}".lower()
        if needle in hay:
            hits.append(
                SearchHit(
                    type="metric",
                    id=0,
                    title=m.label,
                    subtitle=m.description,
                    rank=1.0 if needle in m.label.lower() else 0.5,
                    extra={"key": m.key},
                )
            )
    for d in DIMENSIONS.values():
        hay = f"{d.key} {d.label}".lower()
        if needle in hay:
            hits.append(
                SearchHit(
                    type="dimension",
                    id=0,
                    title=d.label,
                    subtitle=f"Break down or filter by {d.label.lower()}",
                    rank=0.6,
                    extra={"key": d.key},
                )
            )
    hits.sort(key=lambda h: -h.rank)
    return hits[:6]

@router.get("/search", response_model=SearchResponse)
def search(
    _: CurrentUser,
    db: DbSession,
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=5, ge=1, le=20),
    types: str | None = Query(default=None, description="Comma-separated subset of result types"),
) -> SearchResponse:
    q = q.strip()
    wanted = {t.strip() for t in types.split(",")} if types else None
    groups: dict[str, list[SearchHit]] = {}
    for src in _SOURCES:
        if wanted and src.type not in wanted:
            continue
        hits = _search_table(db, src, q, limit)
        if hits:
            groups[src.type] = hits
    if not wanted or wanted & {"metric", "dimension"}:
        for h in _search_catalog(q):
            groups.setdefault(h.type, []).append(h)
    return SearchResponse(query=q, total=sum(len(v) for v in groups.values()), groups=groups)
