"""Import every SQLAlchemy model so Alembic sees complete metadata."""

from travel_agent.modules.access.infrastructure import models as access_models
from travel_agent.modules.conversations import models as conversation_models
from travel_agent.modules.itinerary.infrastructure import models as itinerary_models
from travel_agent.modules.knowledge import models as knowledge_models
from travel_agent.modules.planning.infrastructure import models as planning_models
from travel_agent.modules.tools import models as tool_models
from travel_agent.modules.trips.infrastructure import models as trip_models

__all__ = [
    "access_models",
    "conversation_models",
    "itinerary_models",
    "knowledge_models",
    "planning_models",
    "tool_models",
    "trip_models",
]
