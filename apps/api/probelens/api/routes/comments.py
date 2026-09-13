from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from probelens.api.deps import CurrentUser, DbSession, require
from probelens.core.errors import Forbidden, NotFound
from probelens.core.permissions import Permission
from probelens.models import Comment
from probelens.models.enums import EntityType, Role
from probelens.schemas.investigations import CommentCreate, CommentOut

router = APIRouter(tags=["comments"], dependencies=[Depends(require(Permission.view))])


@router.get("/comments/{entity_type}/{entity_id}", response_model=list[CommentOut])
def list_comments(entity_type: EntityType, entity_id: int, _: CurrentUser, db: DbSession) -> list[Comment]:
    return list(
        db.scalars(
            select(Comment)
            .options(selectinload(Comment.author))
            .where(Comment.entity_type == entity_type.value, Comment.entity_id == entity_id)
            .order_by(Comment.created_at)
        )
    )


@router.post("/comments/{entity_type}/{entity_id}", response_model=CommentOut, status_code=201)
def add_comment(
    entity_type: EntityType, entity_id: int, payload: CommentCreate, user: CurrentUser, db: DbSession
) -> Comment:
    if user.role == Role.viewer:
        raise Forbidden("Viewers can read but not comment")
    comment = Comment(
        entity_type=entity_type.value, entity_id=entity_id, author_id=user.id, body=payload.body.strip()
    )
    db.add(comment)
    db.flush()
    db.refresh(comment)
    return comment


@router.delete("/comments/{comment_id}", status_code=204)
def delete_comment(comment_id: int, user: CurrentUser, db: DbSession) -> None:
    comment = db.get(Comment, comment_id)
    if comment is None:
        raise NotFound("Comment", comment_id)
    if comment.author_id != user.id and user.role != Role.admin:
        raise Forbidden()
    db.delete(comment)
