from __future__ import annotations

from functools import lru_cache
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings
from ..domain.models import Base


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(settings.database_url, future=True)


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True)


def get_db_session() -> Generator[Session, None, None]:
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all() -> None:
    Base.metadata.create_all(bind=get_engine())


def dispose_engine() -> None:
    get_engine().dispose()
