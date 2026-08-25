"""
services/validator.py
~~~~~~~~~~~~~~~~~~~~~~
Validates a payload dict against a JSON Schema using the jsonschema library.
Returns structured errors with dot-notation paths.
"""

from __future__ import annotations

from typing import Any
import jsonschema
from jsonschema import Draft7Validator, ValidationError as JSValidationError


def validate_payload(
    payload: dict[str, Any],
    schema: dict[str, Any],
) -> list[dict[str, str]]:
    """
    Validate *payload* against *schema*.

    Returns a list of error dicts:
        [{"path": "user.email", "message": "'foo' is not a 'email'"}]

    An empty list means the payload is valid.
    """
    validator = Draft7Validator(schema)
    errors: list[dict[str, str]] = []

    for error in sorted(validator.iter_errors(payload), key=lambda e: e.path):
        path = _format_path(error)
        errors.append({"path": path, "message": error.message})

    return errors


def validate_response_against_schema(
    response_body: Any,
    schema: dict[str, Any],
) -> list[dict[str, str]]:
    """Same as validate_payload but accepts any JSON-able value as input."""
    return validate_payload(response_body, schema)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_path(error: JSValidationError) -> str:
    """Convert jsonschema deque path to dot-notation string."""
    parts = list(error.absolute_path)
    if not parts:
        return "$root"
    segments = []
    for part in parts:
        if isinstance(part, int):
            segments.append(f"[{part}]")
        else:
            segments.append(str(part))
    # Build dot-notation, flatten array indices
    path = ""
    for seg in segments:
        if seg.startswith("["):
            path += seg
        else:
            path = f"{path}.{seg}" if path else seg
    return path
