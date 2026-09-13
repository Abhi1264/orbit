"""Product operations: SOPs and their checklists, the knowledge base, and feedback intake."""

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from probelens.api.deps import CurrentUser, DbSession, require
from probelens.api.routes.releases import checklist_out
from probelens.core.errors import BadRequest, NotFound
from probelens.core.permissions import Permission
from probelens.models import (
    Checklist,
    Decision,
    Experiment,
    Feedback,
    Investigation,
    KnowledgeDocument,
    Release,
    Sop,
    Stakeholder,
)
from probelens.models.enums import ChecklistStatus, FeedbackStatus
from probelens.schemas.ops import (
    ChecklistCreate,
    ChecklistItemToggle,
    ChecklistOut,
    EntityRef,
    FeedbackCreate,
    FeedbackOut,
    FeedbackUpdate,
    KnowledgeCreate,
    KnowledgeOut,
    KnowledgeSummary,
    KnowledgeUpdate,
    SopCreate,
    SopOut,
    SopUpdate,
    StakeholderRef,
    ThemeSummary,
)
from probelens.services.projects import default_project_id

router = APIRouter(prefix="/ops", tags=["ops"], dependencies=[Depends(require(Permission.view))])

_write = Depends(require(Permission.manage_ops))

# --------------------------------------------------------------------------- SOPs


def _sop_out(sop: Sop, runs: int) -> SopOut:
    return SopOut(
        id=sop.id,
        title=sop.title,
        description=sop.description,
        category=sop.category,
        owner=sop.owner,
        items=list(sop.items or []),
        run_count=runs,
        updated_at=sop.updated_at,
    )


def _run_counts(db: Session, sop_ids: list[int]) -> dict[int, int]:
    if not sop_ids:
        return {}
    rows = db.execute(
        select(Checklist.sop_id, func.count()).where(Checklist.sop_id.in_(sop_ids)).group_by(Checklist.sop_id)
    ).all()
    return {sid: n for sid, n in rows}


@router.get("/sops", response_model=list[SopOut])
def list_sops(_: CurrentUser, db: DbSession) -> list[SopOut]:
    sops = db.scalars(select(Sop).options(selectinload(Sop.owner)).order_by(Sop.category, Sop.title)).all()
    runs = _run_counts(db, [s.id for s in sops])
    return [_sop_out(s, runs.get(s.id, 0)) for s in sops]


def _load_sop(db: Session, sop_id: int) -> Sop:
    sop = db.get(Sop, sop_id, options=[selectinload(Sop.owner)])
    if sop is None:
        raise NotFound("SOP", sop_id)
    return sop


@router.get("/sops/{sop_id}", response_model=SopOut)
def get_sop(sop_id: int, _: CurrentUser, db: DbSession) -> SopOut:
    sop = _load_sop(db, sop_id)
    return _sop_out(sop, _run_counts(db, [sop.id]).get(sop.id, 0))


def _check_item_keys(items: list) -> None:
    keys = [i.key for i in items]
    if len(set(keys)) != len(keys):
        raise BadRequest("Checklist item keys must be unique")


@router.post("/sops", response_model=SopOut, status_code=201, dependencies=[_write])
def create_sop(payload: SopCreate, user: CurrentUser, db: DbSession) -> SopOut:
    _check_item_keys(payload.items)
    sop = Sop(
        project_id=default_project_id(db),
        title=payload.title.strip(),
        description=payload.description.strip(),
        category=payload.category.strip(),
        owner_id=user.id,
        items=[i.model_dump() for i in payload.items],
    )
    db.add(sop)
    db.flush()
    return _sop_out(_load_sop(db, sop.id), 0)


@router.patch("/sops/{sop_id}", response_model=SopOut, dependencies=[_write])
def update_sop(sop_id: int, payload: SopUpdate, _: CurrentUser, db: DbSession) -> SopOut:
    sop = _load_sop(db, sop_id)
    data = payload.model_dump(exclude_unset=True)
    if "items" in data and payload.items is not None:
        _check_item_keys(payload.items)
        data["items"] = [i.model_dump() for i in payload.items]
    for k, v in data.items():
        setattr(sop, k, v)
    db.flush()
    return _sop_out(sop, _run_counts(db, [sop.id]).get(sop.id, 0))


# --------------------------------------------------------------------------- checklists


def _load_checklist(db: Session, checklist_id: int) -> Checklist:
    c = db.get(Checklist, checklist_id, options=[selectinload(Checklist.owner)])
    if c is None:
        raise NotFound("Checklist", checklist_id)
    return c


@router.get("/checklists", response_model=list[ChecklistOut])
def list_checklists(
    _: CurrentUser,
    db: DbSession,
    status: ChecklistStatus | None = Query(default=None),
    release_id: int | None = Query(default=None),
) -> list[ChecklistOut]:
    stmt = select(Checklist).options(selectinload(Checklist.owner)).order_by(Checklist.updated_at.desc())
    if status:
        stmt = stmt.where(Checklist.status == status)
    if release_id:
        stmt = stmt.where(Checklist.release_id == release_id)
    return [checklist_out(c) for c in db.scalars(stmt).all()]


@router.post("/checklists", response_model=ChecklistOut, status_code=201, dependencies=[_write])
def create_checklist(payload: ChecklistCreate, user: CurrentUser, db: DbSession) -> ChecklistOut:
    sop = _load_sop(db, payload.sop_id)
    title = payload.title
    if payload.release_id is not None:
        rel = db.get(Release, payload.release_id)
        if rel is None:
            raise NotFound("Release", payload.release_id)
        title = title or f"{rel.version} {rel.platform} — {sop.title}"
    title = title or f"{sop.title} — {date.today():%d %b}"
    c = Checklist(
        sop_id=sop.id,
        release_id=payload.release_id,
        title=title,
        owner_id=user.id,
        status=ChecklistStatus.not_started,
        items=[{**item, "done": False, "owner_id": None, "done_at": None} for item in (sop.items or [])],
    )
    db.add(c)
    db.flush()
    return checklist_out(_load_checklist(db, c.id))


@router.patch("/checklists/{checklist_id}/items/{key}", response_model=ChecklistOut, dependencies=[_write])
def toggle_checklist_item(
    checklist_id: int, key: str, payload: ChecklistItemToggle, user: CurrentUser, db: DbSession
) -> ChecklistOut:
    c = _load_checklist(db, checklist_id)
    items = [dict(i) for i in (c.items or [])]
    hit = next((i for i in items if i.get("key") == key), None)
    if hit is None:
        raise NotFound("Checklist item", key)
    hit["done"] = payload.done
    hit["owner_id"] = user.id if payload.done else None
    hit["done_at"] = datetime.now(UTC).isoformat() if payload.done else None
    c.items = items  # reassign so the JSONB change is detected
    done = sum(1 for i in items if i.get("done"))
    c.status = (
        ChecklistStatus.complete
        if done == len(items)
        else ChecklistStatus.in_progress
        if done
        else ChecklistStatus.not_started
    )
    db.flush()
    return checklist_out(c)


# --------------------------------------------------------------------------- knowledge


def _excerpt(body: str, n: int = 180) -> str:
    text = " ".join(line.strip("# ").strip() for line in body.splitlines() if line.strip())
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


@router.get("/knowledge", response_model=list[KnowledgeSummary])
def list_knowledge(
    _: CurrentUser,
    db: DbSession,
    tag: str | None = Query(default=None),
    q: str | None = Query(default=None, min_length=2),
) -> list[KnowledgeSummary]:
    stmt = select(KnowledgeDocument).options(selectinload(KnowledgeDocument.author))
    if tag:
        stmt = stmt.where(KnowledgeDocument.tags.contains([tag]))
    if q:
        ts = func.plainto_tsquery("english", q)
        stmt = stmt.where(KnowledgeDocument.search_vector.op("@@")(ts)).order_by(
            func.ts_rank(KnowledgeDocument.search_vector, ts).desc()
        )
    else:
        stmt = stmt.order_by(KnowledgeDocument.updated_at.desc())
    return [
        KnowledgeSummary(
            id=d.id,
            title=d.title,
            tags=list(d.tags or []),
            author=d.author,
            excerpt=_excerpt(d.body),
            updated_at=d.updated_at,
        )
        for d in db.scalars(stmt).all()
    ]


def _load_doc(db: Session, doc_id: int) -> KnowledgeDocument:
    doc = db.get(KnowledgeDocument, doc_id, options=[selectinload(KnowledgeDocument.author)])
    if doc is None:
        raise NotFound("Document", doc_id)
    return doc


@router.get("/knowledge/{doc_id}", response_model=KnowledgeOut)
def get_knowledge(doc_id: int, _: CurrentUser, db: DbSession) -> KnowledgeDocument:
    return _load_doc(db, doc_id)


@router.post("/knowledge", response_model=KnowledgeOut, status_code=201, dependencies=[_write])
def create_knowledge(payload: KnowledgeCreate, user: CurrentUser, db: DbSession) -> KnowledgeDocument:
    doc = KnowledgeDocument(
        project_id=default_project_id(db),
        title=payload.title.strip(),
        body=payload.body.strip(),
        tags=[t.strip().lower() for t in payload.tags if t.strip()],
        author_id=user.id,
    )
    db.add(doc)
    db.flush()
    return _load_doc(db, doc.id)


@router.patch("/knowledge/{doc_id}", response_model=KnowledgeOut, dependencies=[_write])
def update_knowledge(
    doc_id: int, payload: KnowledgeUpdate, _: CurrentUser, db: DbSession
) -> KnowledgeDocument:
    doc = _load_doc(db, doc_id)
    data = payload.model_dump(exclude_unset=True)
    if "tags" in data and data["tags"] is not None:
        data["tags"] = [t.strip().lower() for t in data["tags"] if t.strip()]
    for k, v in data.items():
        setattr(doc, k, v)
    db.flush()
    return doc


@router.delete("/knowledge/{doc_id}", status_code=204, dependencies=[_write])
def delete_knowledge(doc_id: int, _: CurrentUser, db: DbSession) -> None:
    db.delete(_load_doc(db, doc_id))


# --------------------------------------------------------------------------- feedback

_LINK_MODELS = {
    "investigation": (Investigation, "title"),
    "experiment": (Experiment, "name"),
    "release": (Release, "name"),
    "decision": (Decision, "title"),
}


def _resolve_link(db: Session, etype: str | None, eid: int | None) -> EntityRef | None:
    if not etype or not eid or etype not in _LINK_MODELS:
        return None
    model, title_attr = _LINK_MODELS[etype]
    obj = db.get(model, eid)
    if obj is None:
        return None
    return EntityRef(type=etype, id=eid, title=getattr(obj, title_attr), status=getattr(obj, "status", None))


def _validate_link(db: Session, etype: str | None, eid: int | None) -> None:
    if etype is None and eid is None:
        return
    if etype not in _LINK_MODELS or eid is None:
        raise BadRequest(f"linked_entity_type must be one of {sorted(_LINK_MODELS)} with an id")
    if db.get(_LINK_MODELS[etype][0], eid) is None:
        raise NotFound(etype.capitalize(), eid)


def _feedback_out(db: Session, f: Feedback) -> FeedbackOut:
    return FeedbackOut(
        id=f.id,
        source=f.source,
        theme=f.theme,
        body=f.body,
        sentiment=f.sentiment,
        status=f.status,
        platform=f.platform,
        received_on=f.received_on,
        stakeholder=StakeholderRef.model_validate(f.stakeholder) if f.stakeholder else None,
        submitted_by=f.submitted_by,
        linked=_resolve_link(db, f.linked_entity_type, f.linked_entity_id),
        created_at=f.created_at,
    )


_OPEN_FEEDBACK = (FeedbackStatus.new, FeedbackStatus.triaged, FeedbackStatus.planned)


@router.get("/feedback", response_model=list[FeedbackOut])
def list_feedback(
    _: CurrentUser,
    db: DbSession,
    status: FeedbackStatus | None = Query(default=None),
    theme: str | None = Query(default=None),
    open_only: bool = Query(default=False),
    linked_type: str | None = Query(default=None),
    linked_id: int | None = Query(default=None),
) -> list[FeedbackOut]:
    stmt = (
        select(Feedback)
        .options(selectinload(Feedback.stakeholder), selectinload(Feedback.submitted_by))
        .order_by(Feedback.received_on.desc(), Feedback.id.desc())
    )
    if status:
        stmt = stmt.where(Feedback.status == status)
    if open_only:
        stmt = stmt.where(Feedback.status.in_(_OPEN_FEEDBACK))
    if theme:
        stmt = stmt.where(Feedback.theme == theme)
    if linked_type and linked_id:
        stmt = stmt.where(Feedback.linked_entity_type == linked_type, Feedback.linked_entity_id == linked_id)
    return [_feedback_out(db, f) for f in db.scalars(stmt).all()]


@router.get("/feedback/themes", response_model=list[ThemeSummary])
def feedback_themes(_: CurrentUser, db: DbSession) -> list[ThemeSummary]:
    rows = db.execute(
        select(
            Feedback.theme,
            func.count(),
            func.count().filter(Feedback.status.in_(_OPEN_FEEDBACK)),
            func.count().filter(Feedback.sentiment == "negative"),
            func.max(Feedback.received_on),
        )
        .group_by(Feedback.theme)
        .order_by(func.count().filter(Feedback.status.in_(_OPEN_FEEDBACK)).desc(), func.count().desc())
    ).all()
    return [
        ThemeSummary(theme=t, total=n, open=o, negative=neg, last_received=last)
        for t, n, o, neg, last in rows
    ]


@router.get("/feedback/stakeholders", response_model=list[StakeholderRef])
def list_stakeholders(_: CurrentUser, db: DbSession) -> list[Stakeholder]:
    return list(db.scalars(select(Stakeholder).order_by(Stakeholder.name)))


def _load_feedback(db: Session, feedback_id: int) -> Feedback:
    f = db.get(
        Feedback,
        feedback_id,
        options=[selectinload(Feedback.stakeholder), selectinload(Feedback.submitted_by)],
    )
    if f is None:
        raise NotFound("Feedback", feedback_id)
    return f


@router.post("/feedback", response_model=FeedbackOut, status_code=201, dependencies=[_write])
def create_feedback(payload: FeedbackCreate, user: CurrentUser, db: DbSession) -> FeedbackOut:
    _validate_link(db, payload.linked_entity_type, payload.linked_entity_id)
    if payload.stakeholder_id is not None and db.get(Stakeholder, payload.stakeholder_id) is None:
        raise NotFound("Stakeholder", payload.stakeholder_id)
    f = Feedback(
        project_id=default_project_id(db),
        stakeholder_id=payload.stakeholder_id,
        submitted_by_id=user.id,
        source=payload.source,
        theme=payload.theme.strip().lower().replace(" ", "_"),
        body=payload.body.strip(),
        sentiment=payload.sentiment,
        status=FeedbackStatus.new,
        platform=payload.platform,
        received_on=payload.received_on or date.today(),
        linked_entity_type=payload.linked_entity_type,
        linked_entity_id=payload.linked_entity_id,
    )
    db.add(f)
    db.flush()
    return _feedback_out(db, _load_feedback(db, f.id))


@router.patch("/feedback/{feedback_id}", response_model=FeedbackOut, dependencies=[_write])
def update_feedback(feedback_id: int, payload: FeedbackUpdate, _: CurrentUser, db: DbSession) -> FeedbackOut:
    f = _load_feedback(db, feedback_id)
    data = payload.model_dump(exclude_unset=True)
    unlink = data.pop("unlink", False)
    if unlink:
        f.linked_entity_type = None
        f.linked_entity_id = None
        data.pop("linked_entity_type", None)
        data.pop("linked_entity_id", None)
    elif "linked_entity_type" in data or "linked_entity_id" in data:
        etype = data.get("linked_entity_type", f.linked_entity_type)
        eid = data.get("linked_entity_id", f.linked_entity_id)
        _validate_link(db, etype, eid)
    if data.get("theme"):
        data["theme"] = data["theme"].strip().lower().replace(" ", "_")
    for k, v in data.items():
        setattr(f, k, v)
    db.flush()
    return _feedback_out(db, f)
