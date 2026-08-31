"""Import every SQLAlchemy model so Alembic sees complete metadata."""

from travel_agent.modules.access.infrastructure import models as access_models
from travel_agent.modules.itinerary.infrastructure import models as itinerary_models
from travel_agent.modules.trips.infrastructure import models as trip_models

__all__ = ["access_models", "itinerary_models", "trip_models"]
