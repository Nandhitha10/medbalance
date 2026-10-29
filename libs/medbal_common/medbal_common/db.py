"""Database engine, session factory, and session scope management."""

from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase

from medbal_common.settings import get_settings


class Base(DeclarativeBase):
    pass


_default_engine: Engine | None = None
_default_session_factory: sessionmaker[Session] | None = None


def get_engine(url: str | None = None) -> Engine:
    """Return an SQLAlchemy 2.0 Engine instance."""
    global _default_engine
    if url is not None:
        return create_engine(url, pool_pre_ping=True)
    if _default_engine is None:
        settings = get_settings()
        _default_engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return _default_engine


def get_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    """Return an SQLAlchemy sessionmaker factory."""
    global _default_session_factory
    if engine is not None:
        return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    if _default_session_factory is None:
        eng = get_engine()
        _default_session_factory = sessionmaker(bind=eng, autoflush=False, autocommit=False, expire_on_commit=False)
    return _default_session_factory


@contextmanager
def session_scope(factory: sessionmaker[Session] | None = None) -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""
    session_factory = factory or get_session_factory()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
