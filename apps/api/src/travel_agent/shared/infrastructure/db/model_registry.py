"""Import every SQLAlchemy model so Alembic sees complete metadata."""

from travel_agent.modules.access.infrastructure import models as access_models

__all__ = ["access_models"]
