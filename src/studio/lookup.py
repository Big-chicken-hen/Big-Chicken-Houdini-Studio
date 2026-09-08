"""Installed type discovery on the existing main-thread metadata queue."""
from __future__ import annotations

import fnmatch
import re

from .common import StudioError
from .inspection import bounded_value, optional_bool, optional_call, parameter_template
from .tool_schema import LOOKUP_SCHEMA, validate_schema


def validate_lookup(arguments):
    try:
        validate_schema(arguments, LOOKUP_SCHEMA)
    except StudioError as exc:
        raise StudioError("INVALID_ARGUMENTS", exc.message) from None


def metadata_requests(arguments):
    validate_lookup(arguments)
    if "requests" in arguments:
        return arguments["requests"], True
    request = {key: value for key, value in arguments.items() if key != "source"}
    request.setdefault("category", "Sop")
    request["kind"] = "type" if "type_name" in request else "search"
    if request["kind"] == "search":
        request.setdefault("query", "")
        request.setdefault("include_hidden", True)
        request.setdefault("include_deprecated", True)
        request.setdefault("limit", 80)
    return [request], False


def type_identity(node_type):
    return {"name": node_type.name(), "category": node_type.category().name()}


def type_status(node_type, categories, redact):
    hidden, deprecated = optional_bool(node_type, "hidden"), optional_bool(node_type, "deprecated")
    result = {"hidden": hidden, "deprecated": deprecated,
              "state_source": "installed_hou.OpNodeType", "deprecation": None}
    if deprecated is not True:
        return result
    info = optional_call(node_type, "deprecationInfo")
    record = {"available": isinstance(info, dict), "source": "installed_hou.OpNodeType.deprecationInfo",
              "version": None, "reason": None, "replacement": None}
    if isinstance(info, dict):
        record.update(version=bounded_value(info.get("version"), redact),
                      reason=bounded_value(info.get("reason"), redact))
        replacement = info.get("new_type")
        if replacement is not None:
            try:
                identity = type_identity(replacement)
                category = categories.get(identity["category"])
                present = category.nodeTypes().get(identity["name"]) if category is not None else None
                record["replacement"] = {**identity, "installed": present is not None}
            except Exception:
                record["replacement"] = {"available": False, "reason": "replacement_identity_unavailable"}
        record["metadata_complete"] = bool(info.get("version") and (info.get("reason") or replacement is not None))
    result["deprecation"] = record
    return result


def template_page(node_type, request, redact):
    stack = list(reversed(node_type.parmTemplates()))
    matched = []
    pattern = request.get("parameter_pattern", "*")
    # Enumerate template handles, not scene nodes, runtime instances or values.
    while stack:
        template = stack.pop()
        if fnmatch.fnmatchcase(template.name(), pattern):
            matched.append(template)
        children = optional_call(template, "parmTemplates")
        if children:
            stack.extend(reversed(children))
    matched.sort(key=lambda template: template.name())
    offset, limit = request.get("parameter_offset", 0), request.get("parameter_limit", 16)
    page = matched[offset:offset + limit]
    end = offset + len(page)
    return {"parameters": [parameter_template(template, redact) for template in page],
            "parameter_page": {"pattern": pattern, "offset": offset, "total": len(matched),
                               "next_offset": end if end < len(matched) else None, "truncated": end < len(matched)}}


def installed_lookup(hou, arguments, redact, error):
    requests, batch = metadata_requests(arguments)
    categories = hou.nodeTypeCategories()
    version = hou.applicationVersionString()
    catalogs = {}  # One call only; a later HDA install/uninstall cannot leave stale metadata.
    results = []
    for index, request in enumerate(requests):
        identity = {"index": index, "kind": request["kind"],
                    **{key: request[key] for key in ("category", "query", "type_name") if key in request}}
        try:
            if request["kind"] == "categories":
                result = {"categories": [{"name": name, "label": bounded_value(optional_call(cat, "label"), redact)}
                                         for name, cat in sorted(categories.items())], "total": len(categories), "truncated": False}
            else:
                category_name = next((name for name in categories if name.casefold() == request["category"].casefold()), None)
                if category_name is None:
                    raise StudioError("CATEGORY_NOT_FOUND", "Node category is absent in this installation", 404)
                category = categories[category_name]
                types = category.nodeTypes()
                if request["kind"] == "search":
                    if category_name not in catalogs:
                        catalogs[category_name] = [
                            {**type_identity(nt), "label": bounded_value(nt.description(), redact),
                             "_label": nt.description(), "_aliases": optional_call(nt, "aliases"),
                             **type_status(nt, categories, redact)} for nt in {nt.name(): nt for nt in types.values()}.values()]
                    result = search_types(catalogs[category_name], request, redact)
                else:
                    node_type = types.get(request["type_name"])
                    if node_type is None:
                        raise StudioError("NODE_TYPE_NOT_FOUND", "Exact node type is absent in this installation", 404)
                    aliases = optional_call(node_type, "aliases")
                    definition = optional_call(node_type, "definition")
                    source_path = optional_call(node_type, "sourcePath")
                    native_source = optional_call(node_type, "source")
                    order = optional_call(node_type, "namespaceOrder")
                    result = {**type_identity(node_type), "label": bounded_value(node_type.description(), redact),
                              "name_components": list(node_type.nameComponents()),
                              "aliases": [bounded_value(a, redact) for a in aliases[:16]] if aliases is not None else None,
                              "aliases_truncated": len(aliases) > 16 if aliases is not None else None,
                              "namespace_order": list(order[:16]) if order is not None else None,
                              "namespace_order_truncated": len(order) > 16 if order is not None else None,
                              "min_inputs": optional_call(node_type, "minNumInputs"),
                              "max_inputs": optional_call(node_type, "maxNumInputs"),
                              "max_outputs": optional_call(node_type, "maxNumOutputs"),
                              "child_category": optional_call(optional_call(node_type, "childTypeCategory"), "name"),
                              "source": {"kind": "hda" if definition is not None else "builtin" if source_path == "Internal" else "unknown",
                                         "native": str(native_source) if native_source is not None else None,
                                         "path": bounded_value(source_path, redact)},
                              **type_status(node_type, categories, redact)}
                    if request.get("include_parameters", True):
                        result.update(template_page(node_type, request, redact))
                    if request.get("include_help", True):
                        from .installed_help import installed_help
                        result["help"] = installed_help(hou, node_type, request, redact)
            results.append({**identity, **result, "status": "ok", "houdini_version": version})
        except Exception as exc:
            if not batch:
                raise
            results.append({**identity, "status": "error", "error": {
                **error(exc, "METADATA_UNAVAILABLE"), "index": index,
                "target": {key: identity[key] for key in ("category", "type_name", "query") if key in identity}}})
    if not batch:
        return results[0]
    return {"source": "metadata", "houdini_version": version, "requests": results,
            "status": "partial" if any(result["status"] != "ok" for result in results) else "ok"}


def search_types(catalog, request, redact):
    query = request.get("query", "").strip().casefold()
    words = list(dict.fromkeys(re.findall(r"\w+", query)))[:16]
    matches = []
    filtered = {"hidden": 0, "deprecated": 0, "total": 0}
    for record in catalog:
        names = {"name": [record["name"]], "label": [record["_label"]], "alias": record["_aliases"] or ()}
        hits = {field: {word for word in words if any(word in value.casefold() for value in values)}
                for field, values in names.items()}
        terms = set().union(*hits.values())
        if words and not terms:
            continue
        hidden = record["hidden"] is True and not request.get("include_hidden", False)
        deprecated = record["deprecated"] is True and not request.get("include_deprecated", False)
        filtered["hidden"] += int(hidden)
        filtered["deprecated"] += int(deprecated)
        filtered["total"] += int(hidden or deprecated)
        if hidden or deprecated:
            continue
        exact = 2 if query == record["name"].casefold() else 1 if query in {a.casefold() for a in names["alias"]} else 0
        aliases = record["_aliases"]
        public = {key: value for key, value in record.items() if not key.startswith("_")}
        public.update(aliases=[bounded_value(a, redact) for a in aliases[:16]] if aliases is not None else None,
                      aliases_truncated=len(aliases) > 16 if aliases is not None else None,
                      matched_on=[field for field, terms in hits.items() if terms], matched_terms=sorted(terms))
        matches.append(((-exact, -len(terms), record["name"].casefold(), record["name"]), public))
    matches.sort(key=lambda entry: entry[0])
    offset, limit = request.get("offset", 0), request.get("limit", 12)
    page = matches[offset:offset + limit]
    end = offset + len(page)
    return {"types": [record for _, record in page], "total": len(matches), "offset": offset,
            "next_offset": end if end < len(matches) else None, "truncated": end < len(matches),
            "filters": {"include_hidden": request.get("include_hidden", False),
                        "include_deprecated": request.get("include_deprecated", False),
                        "unknown_state_included": True, "filtered_matches": filtered},
            "matching": "case-insensitive keyword substrings in names, labels and aliases; no help-body search"}
