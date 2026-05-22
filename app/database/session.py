"""Session management helpers for SQLAlchemy."""

from sqlalchemy.orm import declarative_base, sessionmaker

from app.database.connection import engine

Base = declarative_base()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
)


def get_db():
    """Provide a database session for each request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
