"""
JSON Schema validation for request bodies. Loads .json schema files and validates
req.media; raises BadRequestException (400) with detailed errors on failure.
"""
import json
import os
import jsonschema
from jsonschema import ValidationError as JsonSchemaValidationError, Draft7Validator
from exception import BadRequestException

# Use format checker so "email" format is validated
_format_checker = getattr(Draft7Validator, "FORMAT_CHECKER", None)


_SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "..", "schemas")
_CACHE: dict[str, dict] = {}


def _load_schema(name: str) -> dict:
    if name in _CACHE:
        return _CACHE[name]
    path = os.path.join(_SCHEMA_DIR, f"{name}.json")
    if not os.path.isfile(path):
        raise ValueError(f"Schema file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    _CACHE[name] = schema
    return schema


def _format_error(exc: JsonSchemaValidationError) -> list[dict]:
    """Turn jsonschema ValidationError into a list of {path, message} dicts."""
    errors = []
    for err in exc.context if exc.context else [exc]:
        path = ".".join(str(p) for p in err.absolute_path) if err.absolute_path else "body"
        errors.append({"path": path, "message": err.message})
    if not errors:
        errors.append({"path": "body", "message": exc.message})
    return errors


def validate_schema(schema_name: str):
    """
    Falcon before hook factory. Validates req.media against the given JSON schema.
    Raises BadRequestException (400) with detailed error list if validation fails.
    """

    def hook(req, resp, resource, params):
        schema = _load_schema(schema_name)
        try:
            payload = req.media
            if payload is None:
                payload = {}
            validator = Draft7Validator(schema, format_checker=_format_checker) if _format_checker else Draft7Validator(schema)
            validator.validate(payload)
        except JsonSchemaValidationError as e:
            errors = _format_error(e)
            raise BadRequestException(
                title="Validation Error",
                description="Request body failed validation.",
                code="validation_error",
                details=errors,
            ) from e

    return hook


def validate_payload(payload: dict, schema_name: str) -> None:
    """
    Validate a dict against a schema by name. Raises BadRequestException
    with detailed errors if invalid. Use from resources when not using the hook.
    """
    schema = _load_schema(schema_name)
    validator = Draft7Validator(schema, format_checker=_format_checker) if _format_checker else Draft7Validator(schema)
    try:
        validator.validate(payload or {})
    except JsonSchemaValidationError as e:
        errors = _format_error(e)
        raise BadRequestException(
            title="Validation Error",
            description="Request body failed validation.",
            code="validation_error",
            details=errors,
        ) from e
