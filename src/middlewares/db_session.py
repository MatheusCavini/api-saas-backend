"""Falcon middleware for SQLAlchemy session per request."""
from sqlalchemy.orm import sessionmaker, Session


class SQLAlchemySessionManager:
    def __init__(self, db_session_maker: sessionmaker):
        self.db_session_maker = db_session_maker

    def process_request(self, req, resp):
        session: Session = self.db_session_maker()
        req.context.db_session = session

    def process_response(self, req, resp, resource, req_succeeded):
        session = getattr(req.context, "db_session", None)
        if session is not None:
            session.close()
