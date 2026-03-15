"""Business logic and DB operations for sample_entity."""
import logging
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from exception import ConflictException, NotFoundException
from mappers.sample_entity import model_to_response
from models.sample_entity import SampleEntity

class SampleEntityController():
    def __init__(self, db_session):
        self.db_session = db_session
        self.logger = logging.getLogger(__name__)


    def list_entities(self) -> list[dict]:
        entities = self.db_session.query(SampleEntity).order_by(SampleEntity.created_at.desc()).all()
        self.logger.info("Found entities: " + str(entities))
        return [model_to_response(e) for e in entities]


    def get_by_id(self, entity_id: int) -> dict:
        entity = self.db_session.query(SampleEntity).filter(SampleEntity.id == entity_id).first()
        if not entity:
            self.logger.error("Entity with ID " + str(entity_id) + " does not exist.")
            raise NotFoundException(
                title="Not Found",
                description="Sample entity not found.",
            )
        return model_to_response(entity)


    def create(self, payload: dict) -> dict:
        entity = SampleEntity(
            name=payload.get("name", ""),
            email=payload.get("email", ""),
            description=payload.get("description"),
        )
        self.db_session.add(entity)
        try:
            self.db_session.commit()
        except IntegrityError as exc:
            self.db_session.rollback()
            raise ConflictException(
                title="Conflict",
                description="Sample entity with this email already exists.",
            ) from exc
        self.db_session.refresh(entity)
        return model_to_response(entity)


    def update(self, entity_id: int, payload: dict) -> dict:
        entity = self.db_session.query(SampleEntity).filter(SampleEntity.id == entity_id).first()
        if not entity:
            self.logger.error("Entity with ID " + str(entity_id) + " does not exist.")
            raise NotFoundException(
                title="Not Found",
                description="Sample entity not found.",
            )
        for key in ("name", "email", "description"):
            if key in payload:
                setattr(entity, key, payload[key])
        try:
            self.db_session.commit()
        except IntegrityError as exc:
            self.db_session.rollback()
            raise ConflictException(
                title="Conflict",
                description="Sample entity with this email already exists.",
            ) from exc
        self.db_session.refresh(entity)
        return model_to_response(entity)


    def delete(self, entity_id: int) -> None:
        entity = self.db_session.query(SampleEntity).filter(SampleEntity.id == entity_id).first()
        if not entity:
            self.logger.error("Entity with ID " + str(entity_id) + " does not exist.")
            raise NotFoundException(
                title="Not Found",
                description="Sample entity not found.",
            )
        self.db_session.delete(entity)
        self.db_session.commit()
