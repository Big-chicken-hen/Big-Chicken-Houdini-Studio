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



def validate_schema(value, definition, definitions=None):
    definitions = definitions if definitions is not None else definition.get("$defs", {})
    if "$ref" in definition:
        return validate_schema(value, definitions[definition["$ref"].removeprefix("#/$defs/")], definitions)
    if "oneOf" in definition:
        matches = 0
        for option in definition["oneOf"]:
            try:
                validate_schema(value, option, definitions)
                matches += 1
            except StudioError:
                pass
        if matches != 1:
            raise StudioError("INVALID_TOOL_CALL", "Argument must match one declared tool shape")
        return
    kind = definition.get("type")
    valid = {"object": lambda: isinstance(value, dict), "array": lambda: isinstance(value, list),
             "string": lambda: isinstance(value, str), "integer": lambda: type(value) is int,
             "number": lambda: type(value) in (int, float) and math.isfinite(value),
             "boolean": lambda: type(value) is bool, "null": lambda: value is None}
    if (kind in valid and not valid[kind]()) or ("enum" in definition and value not in definition["enum"]):
        raise StudioError("INVALID_TOOL_CALL", "Tool argument type or value does not match the schema")
    if kind == "object":
        properties = definition.get("properties", {})
        if ((definition.get("additionalProperties") is False and set(value) - set(properties)) or
                set(definition.get("required", [])) - set(value)):
            raise StudioError("INVALID_TOOL_CALL", "Tool arguments do not match the schema")
        for key in value.keys() & properties.keys():
            validate_schema(value[key], properties[key], definitions)
    if kind == "array":
        if not definition.get("minItems", 0) <= len(value) <= definition.get("maxItems", MAX_BODY):
            raise StudioError("INVALID_TOOL_CALL", "Invalid array length")
        for item in value:
            validate_schema(item, definition.get("items", {}), definitions)
    if kind == "string":
        if not definition.get("minLength", 0) <= len(value) <= definition.get("maxLength", MAX_BODY):
            raise StudioError("INVALID_TOOL_CALL", "Invalid string length")
        if "pattern" in definition and re.search(definition["pattern"], value) is None:
            raise StudioError("INVALID_TOOL_CALL", "String does not match the declared pattern")
    if kind in {"number", "integer"} and not definition.get("minimum", -math.inf) <= value <= definition.get("maximum", math.inf):
        raise StudioError("INVALID_TOOL_CALL", "Number is outside the permitted range")



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
    "limit": {"type": "integer", "minimum": 1, "maximum": 32, "default": 12},
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
            **SEARCH_OPTIONS, "limit": {"type": "integer", "minimum": 1, "maximum": 80, "default": 80},
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
