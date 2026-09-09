"""The existing bounded schema subset, shared by wire and runtime validation."""
from __future__ import annotations

import math
import re

from .common import StudioError
from .http import MAX_BODY


def schema(properties=None, required=(), definitions=None):
    value = {"type": "object", "properties": properties or {}, "required": list(required), "additionalProperties": False}
    if definitions:
        value["$defs"] = definitions
    return value



def _shape_rank(value, option):
    """Choose an informative failure, never use this to accept an invalid shape."""
    if not isinstance(value, dict):
        return (0, 0, 0)
    properties = option.get("properties", {})
    literals = [value[key] in spec["enum"] for key, spec in properties.items()
                if key in value and "enum" in spec]
    differences = len(set(value) - set(properties)) + len(set(option.get("required", [])) - set(value))
    return (sum(literals), -literals.count(False), -differences)


def validate_schema(value, definition, definitions=None, path="arguments"):
    definitions = definitions if definitions is not None else definition.get("$defs", {})
    def fail(message, **details):
        raise StudioError("INVALID_TOOL_CALL", f"{path}: {message}", field=path, **details)
    if "$ref" in definition:
        return validate_schema(value, definitions[definition["$ref"].removeprefix("#/$defs/")], definitions, path)
    if "oneOf" in definition:
        matches, failures = 0, []
        for option in definition["oneOf"]:
            try:
                validate_schema(value, option, definitions, path)
                matches += 1
            except StudioError as exc:
                failures.append((_shape_rank(value, option), exc))
        if matches == 0 and failures:
            raise max(failures, key=lambda entry: entry[0])[1]
        if matches != 1:
            fail("must match exactly one declared tool shape")
        return
    kind = definition.get("type")
    valid = {"object": lambda: isinstance(value, dict), "array": lambda: isinstance(value, list),
             "string": lambda: isinstance(value, str), "integer": lambda: type(value) is int,
             "number": lambda: type(value) in (int, float) and math.isfinite(value),
             "boolean": lambda: type(value) is bool, "null": lambda: value is None}
    if kind in valid and not valid[kind]():
        fail(f"expected {kind}", expected_type=kind)
    if "enum" in definition and value not in definition["enum"]:
        fail("allowed values: " + ", ".join(str(v) for v in definition["enum"]), allowed=definition["enum"])
    if kind == "object":
        properties = definition.get("properties", {})
        missing = sorted(set(definition.get("required", [])) - set(value))
        if missing:
            fail("missing required fields: " + ", ".join(missing), missing=missing)
        extra = sorted(set(value) - set(properties))
        if definition.get("additionalProperties") is False and extra:
            fail("unknown fields: " + ", ".join(extra), unknown=extra)
        for key in properties:
            if key in value:
                validate_schema(value[key], properties[key], definitions, path + "." + key)
    if kind == "array":
        if not definition.get("minItems", 0) <= len(value) <= definition.get("maxItems", MAX_BODY):
            fail(f"item count must be {definition.get('minItems', 0)}..{definition.get('maxItems', MAX_BODY)}")
        for index, item in enumerate(value):
            validate_schema(item, definition.get("items", {}), definitions, f"{path}[{index}]")
    if kind == "string":
        if not definition.get("minLength", 0) <= len(value) <= definition.get("maxLength", MAX_BODY):
            fail(f"length must be {definition.get('minLength', 0)}..{definition.get('maxLength', MAX_BODY)} characters")
        if "pattern" in definition and re.search(definition["pattern"], value) is None:
            fail("must match pattern " + definition["pattern"])
    if kind in {"number", "integer"} and not definition.get("minimum", -math.inf) <= value <= definition.get("maximum", math.inf):
        bounds = {key: definition[key] for key in ("minimum", "maximum") if key in definition}
        fail("permitted range: " + ", ".join(f"{key}={v}" for key, v in bounds.items()), **bounds)



STRING = {"type": "string"}
TEXT = {"type": "string", "minLength": 1, "maxLength": 256}
OFFSET = {"type": "integer", "minimum": 0, "maximum": 1000000, "default": 0}
BOOLEAN = {"type": "boolean"}
PARAMETER_OPTIONS = {
    "include_parameters": {**BOOLEAN, "default": True},
    "parameter_pattern": {"type": "string", "minLength": 1, "maxLength": 128, "default": "*"},
    "parameter_offset": OFFSET,
    "parameter_limit": {"type": "integer", "minimum": 1, "maximum": 64, "default": 16},
    "include_help": {**BOOLEAN, "default": True},
    "help_offset": {"type": "integer", "minimum": 0, "maximum": 262144, "default": 0},
    "help_limit": {"type": "integer", "minimum": 1, "maximum": 8192, "default": 2048},
}
SEARCH_OPTIONS = {
    "offset": OFFSET,
    "limit": {"type": "integer", "minimum": 1, "maximum": 80, "default": 12},
    "include_hidden": {**BOOLEAN, "default": False},
    "include_deprecated": {**BOOLEAN, "default": False},
}
METADATA_REQUEST = {"oneOf": [
    schema({"kind": {"enum": ["categories"]}}, ["kind"]),
    schema({"kind": {"enum": ["search"]}, "category": TEXT,
            "query": {"type": "string", "minLength": 1, "maxLength": 128, "pattern": r"\w"}, **SEARCH_OPTIONS},
           ["kind", "category", "query"]),
    schema({"kind": {"enum": ["type"]}, "category": TEXT, "type_name": TEXT, **PARAMETER_OPTIONS},
           ["kind", "category", "type_name"]),
]}
LOOKUP_SCHEMA = {"type": "object", "oneOf": [
    schema({"source": {"enum": ["metadata"]},
            "requests": {"type": "array", "minItems": 1, "maxItems": 4,
                         "items": {"$ref": "#/$defs/metadata_request"}}}, ["source", "requests"]),
    # Thin compatibility shapes retain flat metadata calls and their result keys.
    schema({"source": {"enum": ["metadata"]}, "category": {**TEXT, "default": "Sop"},
            "query": {"type": "string", "maxLength": 128, "default": ""},
            **SEARCH_OPTIONS,
            "include_hidden": {**BOOLEAN, "default": True}, "include_deprecated": {**BOOLEAN, "default": True}}),
    schema({"source": {"enum": ["metadata"]}, "category": {**TEXT, "default": "Sop"},
            "type_name": TEXT, **PARAMETER_OPTIONS}, ["type_name"]),
    schema({"source": {"enum": ["hom"]}, "symbol": TEXT,
            "members": {"type": "boolean", "enum": [False], "default": False}}, ["source", "symbol"]),
    schema({"source": {"enum": ["hom"]}, "symbol": TEXT,
            "members": {"type": "boolean", "enum": [True]},
            "query": {"type": "string", "maxLength": 128, "default": ""}, "offset": OFFSET,
            "limit": {"type": "integer", "minimum": 1, "maximum": 64, "default": 32}},
           ["source", "symbol", "members"]),
    schema({"source": {"enum": ["documents"]}, "query": STRING, "version": STRING}, ["source"]),
], "$defs": {"metadata_request": METADATA_REQUEST}}
