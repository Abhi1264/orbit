from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from probelens.config import get_settings

@lru_cache
def get_engine():
    return create_engine(get_settings().database_url, pool_pre_ping=True, pool_size=5, max_overflow=10)

@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)

def get_db() -> Generator[Session, None, None]:
    db = get_sessionmaker()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
