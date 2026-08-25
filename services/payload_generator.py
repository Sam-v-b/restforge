"""
services/payload_generator.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Generates sample request payloads from a JSON Schema.

Supported modes:
    sample      — sensible, readable default values
    edge_case   — boundary / stress values (empty strings, min/max ints, etc.)
    random      — randomised within schema constraints

Supports JSON Schema draft-07 constructs:
    type, properties, required, items, enum, format,
    minimum/maximum, minLength/maxLength, anyOf, oneOf, allOf, $ref (local only)
"""

from __future__ import annotations

import random
import string
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_payload(
    schema: dict[str, Any],
    mode: str = "sample",
    seed: Optional[int] = None,
) -> tuple[dict[str, Any], list[str]]:
    """
    Generate a payload dict from *schema*.

    Returns:
        (payload, warnings) — payload is the generated object,
                              warnings is a list of human-readable notices.
    """
    rng = random.Random(seed)
    ctx = _GeneratorContext(mode=mode, rng=rng)
    result = ctx.generate(schema)

    # Root should always be an object for REST payloads, but we tolerate
    # schemas that describe a scalar or array root.
    if not isinstance(result, dict):
        result = {"value": result}

    return result, ctx.warnings


# ---------------------------------------------------------------------------
# Internal context
# ---------------------------------------------------------------------------

class _GeneratorContext:
    def __init__(self, mode: str, rng: random.Random):
        self.mode = mode
        self.rng = rng
        self.warnings: list[str] = []
        self._definitions: dict[str, Any] = {}   # for $defs / definitions
        self._depth = 0

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def generate(self, schema: dict[str, Any]) -> Any:
        self._depth += 1
        if self._depth > 10:
            self.warnings.append("Schema recursion limit reached; returning None for deep node.")
            self._depth -= 1
            return None

        # Cache $defs / definitions at top level
        if "$defs" in schema:
            self._definitions.update(schema["$defs"])
        if "definitions" in schema:
            self._definitions.update(schema["definitions"])

        result = self._dispatch(schema)
        self._depth -= 1
        return result

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, schema: dict[str, Any]) -> Any:
        # $ref resolution (local only)
        if "$ref" in schema:
            return self._resolve_ref(schema["$ref"], schema)

        # Composition keywords
        if "allOf" in schema:
            return self._handle_all_of(schema)
        if "anyOf" in schema:
            return self._handle_any_of(schema["anyOf"])
        if "oneOf" in schema:
            return self._handle_one_of(schema["oneOf"])

        # enum shortcut
        if "enum" in schema:
            return self._pick_enum(schema["enum"])

        # const
        if "const" in schema:
            return schema["const"]

        schema_type = schema.get("type")

        if schema_type is None:
            # No type — try to infer from properties
            if "properties" in schema:
                schema_type = "object"
            else:
                self.warnings.append("Schema node has no 'type'; returning None.")
                return None

        # Handle union types: "type": ["string", "null"]
        if isinstance(schema_type, list):
            non_null = [t for t in schema_type if t != "null"]
            schema_type = non_null[0] if non_null else "null"

        dispatch = {
            "object":  self._gen_object,
            "array":   self._gen_array,
            "string":  self._gen_string,
            "integer": self._gen_integer,
            "number":  self._gen_number,
            "boolean": self._gen_boolean,
            "null":    lambda s: None,
        }

        handler = dispatch.get(schema_type)
        if handler is None:
            self.warnings.append(f"Unknown schema type {schema_type!r}; returning None.")
            return None

        return handler(schema)

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def _handle_all_of(self, schema: dict[str, Any]) -> Any:
        """Merge all sub-schemas (assuming object types)."""
        merged: dict[str, Any] = {}
        for sub in schema.get("allOf", []):
            value = self.generate(sub)
            if isinstance(value, dict):
                merged.update(value)
        # Apply top-level properties if present
        if "properties" in schema:
            top = self._gen_object(schema)
            if isinstance(top, dict):
                merged.update(top)
        return merged or self.generate({**schema, "allOf": None})  # type: ignore[arg-type]

    def _handle_any_of(self, sub_schemas: list[dict]) -> Any:
        sub = self.rng.choice(sub_schemas)
        return self.generate(sub)

    def _handle_one_of(self, sub_schemas: list[dict]) -> Any:
        sub = self.rng.choice(sub_schemas)
        return self.generate(sub)

    def _resolve_ref(self, ref: str, original_schema: dict[str, Any]) -> Any:
        if ref.startswith("#/$defs/"):
            key = ref[len("#/$defs/"):]
            if key in self._definitions:
                return self.generate(self._definitions[key])
        if ref.startswith("#/definitions/"):
            key = ref[len("#/definitions/"):]
            if key in self._definitions:
                return self.generate(self._definitions[key])
        self.warnings.append(f"Cannot resolve $ref {ref!r}; returning None.")
        return None

    # ------------------------------------------------------------------
    # Type generators
    # ------------------------------------------------------------------

    def _gen_object(self, schema: dict[str, Any]) -> dict[str, Any]:
        properties: dict[str, Any] = schema.get("properties", {})
        required: list[str] = schema.get("required", [])
        result: dict[str, Any] = {}

        for prop_name, prop_schema in properties.items():
            # In edge_case mode, omit optional fields half the time
            if self.mode == "edge_case" and prop_name not in required:
                if self.rng.random() < 0.5:
                    continue
            result[prop_name] = self.generate(prop_schema)

        # Ensure all required fields are present
        for req in required:
            if req not in result and req in properties:
                result[req] = self.generate(properties[req])

        return result

    def _gen_array(self, schema: dict[str, Any]) -> list[Any]:
        items_schema = schema.get("items", {"type": "string"})
        min_items: int = schema.get("minItems", 1)
        max_items: int = schema.get("maxItems", 3)

        if self.mode == "edge_case":
            count = min_items  # minimum length
        elif self.mode == "random":
            count = self.rng.randint(min_items, max(min_items, max_items))
        else:
            count = max(1, min_items)

        return [self.generate(items_schema) for _ in range(count)]

    def _gen_string(self, schema: dict[str, Any]) -> str:
        fmt = schema.get("format")
        min_len: int = schema.get("minLength", 1)
        max_len: int = schema.get("maxLength", 30)

        # Format-aware generation
        if fmt == "email":
            return self._sample_email()
        if fmt in ("uri", "url"):
            return "https://example.com/resource"
        if fmt == "uuid":
            return str(uuid.UUID(int=self.rng.getrandbits(128)))
        if fmt == "date":
            return date.today().isoformat()
        if fmt in ("date-time", "datetime"):
            return datetime.now(timezone.utc).isoformat()
        if fmt == "ipv4":
            return ".".join(str(self.rng.randint(1, 254)) for _ in range(4))
        if fmt == "hostname":
            return "example.com"
        if fmt == "password":
            return "Passw0rd!23"

        # enum shortcut already handled in _dispatch

        if self.mode == "edge_case":
            if min_len == 0:
                return ""          # empty string edge case
            return "a" * min_len   # minimum-length string

        if self.mode == "random":
            length = self.rng.randint(min_len, max(min_len, max_len))
            return "".join(self.rng.choices(string.ascii_lowercase + string.digits, k=length))

        # sample mode — use field name hints if available
        return f"sample_{self.rng.randint(1000, 9999)}"

    def _gen_integer(self, schema: dict[str, Any]) -> int:
        lo: int = schema.get("minimum", schema.get("exclusiveMinimum", 0))
        hi: int = schema.get("maximum", schema.get("exclusiveMaximum", 100))

        if isinstance(lo, float): lo = int(lo)
        if isinstance(hi, float): hi = int(hi)
        lo, hi = min(lo, hi), max(lo, hi)

        if self.mode == "edge_case":
            return self.rng.choice([lo, hi])
        if self.mode == "random":
            return self.rng.randint(lo, hi)
        return max(lo, 1)   # sample: sensible positive default

    def _gen_number(self, schema: dict[str, Any]) -> float:
        lo: float = float(schema.get("minimum", schema.get("exclusiveMinimum", 0.0)))
        hi: float = float(schema.get("maximum", schema.get("exclusiveMaximum", 100.0)))
        lo, hi = min(lo, hi), max(lo, hi)

        if self.mode == "edge_case":
            return self.rng.choice([lo, hi])
        if self.mode == "random":
            return round(self.rng.uniform(lo, hi), 4)
        return round((lo + hi) / 2, 2)

    def _gen_boolean(self, schema: dict[str, Any]) -> bool:
        if self.mode == "random":
            return self.rng.choice([True, False])
        return True

    def _pick_enum(self, values: list[Any]) -> Any:
        if self.mode == "random":
            return self.rng.choice(values)
        return values[0]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _sample_email(self) -> str:
        local = "".join(self.rng.choices(string.ascii_lowercase, k=self.rng.randint(4, 10)))
        domain = self.rng.choice(["example.com", "test.org", "mail.net"])
        return f"{local}@{domain}"
