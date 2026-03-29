"""Business logic and DB operations for roles."""
import logging

from mappers.role import model_to_response as role_to_response
from models.role import Role


class RoleController:
    def __init__(self, db_session):
        self.db_session = db_session
        self.logger = logging.getLogger(__name__)

    def list_available(self) -> list[dict]:
        roles = (
            self.db_session.query(Role)
            .order_by(Role.name.asc())
            .all()
        )
        self.logger.info("Found %s available roles", len(roles))
        return [role_to_response(role) for role in roles]
