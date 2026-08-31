from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Infrastructure-only SQLAlchemy metadata root."""
