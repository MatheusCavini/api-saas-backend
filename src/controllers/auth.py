"""Authentication controller functions."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from exception import ConflictException, NotAuthorizedException, ServiceUnavailableException
from models.user import User
from typing import TypedDict

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
logger = logging.getLogger(__name__)


class RegisterRequest(TypedDict):
    email: str
    password: str


class LoginRequest(TypedDict):
    email: str
    password: str


class OAuthRequest(TypedDict):
    token: str


def _get_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET", "").strip()
    if not secret:
        logger.error("JWT secret is not configured")
        raise ServiceUnavailableException(
            title="Service Unavailable",
            description="JWT secret is not configured.",
        )
    return secret


def _get_jwt_algorithm() -> str:
    return os.environ.get("JWT_ALGORITHM", "HS256").strip() or "HS256"


def create_access_token(user_entity_key: UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_entity_key),
        "iat": now,
        "exp": now + timedelta(hours=24),
    }
    token = jwt.encode(payload, _get_jwt_secret(), algorithm=_get_jwt_algorithm())
    return token


def register_user(session: Session, data: RegisterRequest) -> dict:
    logger.info("Registering new user")
    password_hash = _pwd_context.hash(data["password"])
    user = User(
        username=data["name"],
        email=data["email"],
        password_hash=password_hash,
        deactivated_on=None,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        logger.warning("Registration failed: user already exists")
        raise ConflictException(
            title="Conflict",
            description="A user with this email already exists.",
        ) from exc
    session.refresh(user)
    logger.info("User registration successful: user_key=%s", user.user_key)
    access_token = create_access_token(user.user_key)
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "user_key": str(user.user_key),
    }


def login_user(session: Session, data: LoginRequest) -> dict:
    user = (
        session.query(User)
        .filter(User.email == data["email"])
        .filter(User.deactivated_on.is_(None))
        .first()
    )
    if not user or not _pwd_context.verify(data["password"], user.password_hash):
        logger.warning("Login failed: invalid credentials")
        raise NotAuthorizedException(
            title="Unauthorized",
            description="Invalid email or password.",
        )
    logger.info("Login successful: user_key=%s", user.user_key)
    access_token = create_access_token(user.user_key)
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "user_key": str(user.user_key),
    }


def google_oauth_login(session: Session, data: OAuthRequest) -> dict:
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    if not client_id:
        logger.error("Google OAuth client ID is not configured")
        raise ServiceUnavailableException(
            title="Service Unavailable",
            description="Google OAuth client ID is not configured.",
        )

    try:
        id_info = id_token.verify_oauth2_token(data["token"], Request(), audience=client_id)
    except ValueError as exc:
        logger.warning("Google OAuth login failed: invalid ID token")
        raise NotAuthorizedException(
            title="Unauthorized",
            description="Invalid Google ID token.",
        ) from exc

    email = id_info.get("email")
    _name = id_info.get("name")
    if not email:
        logger.warning("Google OAuth login failed: token missing email")
        raise NotAuthorizedException(
            title="Unauthorized",
            description="Google ID token did not contain an email.",
        )

    user = (
        session.query(User)
        .filter(User.email == email)
        .filter(User.deactivated_on.is_(None))
        .first()
    )
    if not user:
        logger.info("Google OAuth: creating new user")
        dummy_password = f"oauth-{uuid4().hex}"
        user = User(
            username=email,
            email=email,
            password_hash=_pwd_context.hash(dummy_password),
            deactivated_on=None,
        )
        session.add(user)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            user = (
                session.query(User)
                .filter(User.email == email)
                .filter(User.deactivated_on.is_(None))
                .first()
            )
            if not user:
                logger.warning("Google OAuth registration failed: user already exists")
                raise ConflictException(
                    title="Conflict",
                    description="A user with this email already exists.",
                )
        else:
            session.refresh(user)
            logger.info("Google OAuth registration successful: user_key=%s", user.user_key)
    else:
        logger.info("Google OAuth login successful: user_key=%s", user.user_key)

    access_token = create_access_token(user.user_key)
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "user_key": str(user.user_key),
    }
