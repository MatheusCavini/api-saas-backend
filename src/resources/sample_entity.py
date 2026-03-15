"""Falcon resource for sample_entity. HTTP parsing and response only; delegates to controller."""
import falcon
import logging

from controllers.sample_entity import SampleEntityController
from exception import BadRequestException
from utils.validator import validate_payload


class SampleEntityResource:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def on_get(self, req, resp, entity_id=None):
        sample_entity_controller = SampleEntityController(req.context.db_session)
        if entity_id is not None:
            self.logger.info("Processing GET request for entity with ID" + str(entity_id))
            try:
                eid = int(entity_id)
            except ValueError:
                raise BadRequestException(
                    title="Bad Request",
                    description="Invalid entity id.",
                )
            resp.media = sample_entity_controller.get_by_id(eid)
            resp.status = falcon.HTTP_200
        else:
            self.logger.info("Processing GET request for entities")
            resp.media = sample_entity_controller.list_entities()
            resp.status = falcon.HTTP_200

    def on_post(self, req, resp):
        sample_entity_controller = SampleEntityController(req.context.db_session)
        self.logger.info("Processinf POST request for entity")
        payload = req.media or {}
        validate_payload(payload, "sample_entity_create")
        resp.media = sample_entity_controller.create(payload)
        resp.status = falcon.HTTP_201

    def on_put(self, req, resp, entity_id):
        self.logger.info("Processing PUT request for entity with ID" + str(entity_id))
        try:
            eid = int(entity_id)
        except (ValueError, TypeError):
            raise BadRequestException(
                title="Bad Request",
                description="Invalid entity id.",
            )
        sample_entity_controller = SampleEntityController(req.context.db_session)
        payload = req.media or {}
        validate_payload(payload, "sample_entity_update")
        resp.media = sample_entity_controller.update(eid, payload)
        resp.status = falcon.HTTP_200

    def on_patch(self, req, resp, entity_id):
        self.on_put(req, resp, entity_id)

    def on_delete(self, req, resp, entity_id):
        self.logger.info("Processing DELETE request for entity with ID" + str(entity_id))
        sample_entity_controller = SampleEntityController(req.context.db_session)
        try:
            eid = int(entity_id)
        except (ValueError, TypeError):
            raise BadRequestException(
                title="Bad Request",
                description="Invalid entity id.",
            )
        sample_entity_controller.delete(eid)
        resp.status = falcon.HTTP_204
