from sqlalchemy import select
from sqlalchemy.orm import Session

from probelens.models import Project


def default_project_id(db: Session) -> int:
    """The app is single-project today; every object is attached to the first project."""
    project_id = db.scalar(select(Project.id).order_by(Project.id).limit(1))
    if project_id is None:
        raise RuntimeError("No project exists; run the seed first")
    return project_id
