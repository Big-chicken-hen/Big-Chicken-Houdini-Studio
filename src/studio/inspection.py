"""Targeted native parameter discovery and bounded geometry element samples."""
from __future__ import annotations

import math


def optional_call(obj, method, *args):
    """Only named, known metadata methods; unavailable facts remain null."""
    try:
        callback = getattr(obj, method, None)
        return callback(*args) if callable(callback) else None
    except Exception:
        return None


def optional_bool(obj, method):
    value = optional_call(obj, method)
    return value if type(value) is bool else None


def node_identity(node):
    parent = optional_call(node, "parent")
    return {"path": node.path(), "name": node.name(), "type": node.type().name(),
            "category": optional_call(node.type().category(), "name"),
            "parent": optional_call(parent, "path")}


def node_record(node, redact=lambda text: text):
    result = node_identity(node)
    inputs, connections = optional_call(node, "inputs"), optional_call(node, "inputConnections")
    result.update(inputs=[n.path() if n else None for n in inputs[:200]] if inputs is not None else None,
                  inputs_total=len(inputs) if inputs is not None else None,
                  inputs_truncated=len(inputs) > 200 if inputs is not None else None,
                  connections=None, position=None,
                  flags={key: optional_bool(node, method) for key, method in {
                      "display": "isDisplayFlagSet", "render": "isRenderFlagSet",
                      "bypass": "isBypassed", "template": "isTemplateFlagSet"}.items()},
                  editability={"network_contents": optional_bool(node, "isEditable"),
                               "inside_locked_asset": optional_bool(node, "isInsideLockedHDA"),
                               "editable_inside_locked_asset": optional_bool(node, "isEditableInsideLockedHDA")},
                  cook={"needs_cook": optional_bool(node, "needsToCook"),
                        "cook_count": optional_call(node, "cookCount"), "verified_by_this_read": False,
                        "diagnostics_source": "last_cook"})
    if connections is not None:
        result["connections"] = [{"source": optional_call(c.inputNode(), "path"),
                                  "source_output_index": c.outputIndex(),
                                  "destination_input_index": c.inputIndex()} for c in connections[:200]]
        result["connections_total"] = len(connections)
        result["connections_truncated"] = len(connections) > 200
    position = optional_call(node, "position")
    if position is not None:
        result["position"] = list(position)
    for name in ("errors", "warnings"):
        values = optional_call(node, name)
        result[name] = [bounded_value(v, redact) for v in values[:8]] if values is not None else None
        result[name + "_truncated"] = len(values) > 8 if values is not None else None
    return result


def network_record(node):
    category = optional_call(node, "childTypeCategory")
    return {"path": node.path(), "child_category": optional_call(category, "name"),
            "editable": optional_bool(node, "isEditable"),
            "display_output": optional_call(optional_call(node, "displayNode"), "path"),
            "render_output": optional_call(optional_call(node, "renderNode"), "path")}


def working_context(hou):
    selected = optional_call(hou, "selectedNodes")
    nodes = []
    for node in (selected or ())[:16]:
        try:
            nodes.append(node_identity(node))
        except Exception:
            nodes.append({"path": optional_call(node, "path"), "status": "unavailable"})
    selection = {"available": selected is not None, "total": len(selected) if selected is not None else None,
                 "truncated": len(selected) > 16 if selected is not None else None, "nodes": nodes}
    network = {"path": None, "child_category": None, "editable": None,
               "display_output": None, "render_output": None, "available": False,
               "source": "no_ui", "observed": False, "fallback_path": "/obj"}
    if optional_bool(hou, "isUIAvailable") is True:
        ui, pane_type = getattr(hou, "ui", None), getattr(hou, "paneTabType", None)
        pane = optional_call(ui, "paneTabOfType", getattr(pane_type, "NetworkEditor", None))
        network["source"] = "no_network_editor" if pane is None else "first_network_editor"
        pwd = optional_call(pane, "pwd")
        if pwd is not None:
            network.update(network_record(pwd), available=True, observed=True, fallback_path=None,
                           pane_name=optional_call(pane, "name"))
    playbar, takes = getattr(hou, "playbar", None), getattr(hou, "takes", None)
    frame_range = optional_call(playbar, "frameRange")
    playback_range = optional_call(playbar, "playbackRange")
    return {"selected": [n.path() for n in (selected or ())[:64]], "selection_summary": selection,
            "network": network["path"] or "/obj", "network_summary": network,
            "fps": optional_call(hou, "fps"),
            "frame_range": list(frame_range) if frame_range is not None else None,
            "playback_range": list(playback_range) if playback_range is not None else None,
            "take": optional_call(optional_call(takes, "currentTake"), "name")}


def bounded_value(value, redact=lambda text: text):
    if isinstance(value, str):
        value = redact(value)
        return value if len(value) <= 512 else {"text": value[:512], "truncated": True}
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, (tuple, list)) and len(value) <= 16:
        return [bounded_value(v, redact) for v in value]
    return {"omitted": "Non-scalar or oversized value; use a targeted HOM read if needed"}


def parameter_template(template, redact=lambda text: text):
    """Static template facts only: never call a Parm's dynamic menu methods."""
    data_type = optional_call(template, "dataType")
    result = {"name": template.name(), "template_name": template.name(), "name_kind": "template_pattern",
              "label": bounded_value(template.label(), redact), "type": str(template.type()),
              "data_type": str(data_type) if data_type is not None else None,
              "components": template.numComponents(),
              "default": bounded_value(optional_call(template, "defaultValue"), redact),
              "help": bounded_value(optional_call(template, "help"), redact),
              "range": None, "menu": None}
    minimum, maximum = optional_call(template, "minValue"), optional_call(template, "maxValue")
    if minimum is not None or maximum is not None:
        result["range"] = {"min": bounded_value(minimum), "max": bounded_value(maximum),
                           "min_strict": optional_bool(template, "minIsStrict"),
                           "max_strict": optional_bool(template, "maxIsStrict")}
    items, labels = optional_call(template, "menuItems"), optional_call(template, "menuLabels")
    if items is not None:
        generator = optional_call(template, "itemGeneratorScript")
        result["menu"] = {"items": [{"token": bounded_value(token, redact),
                                      "label": bounded_value(labels[i], redact) if labels and i < len(labels) else None,
                                      "index": i} for i, token in enumerate(items[:32])],
                          "total": len(items), "truncated": len(items) > 32,
                          "use_token": optional_bool(template, "menuUseToken"),
                          "dynamic": bool(generator) if isinstance(generator, str) else None,
                          "dynamic_evaluated": False, "source": "static_template"}
    return result


def parameter_instances(node, view, redact=lambda text: text, *, strict=True):
    # HOM returns matching parameter handles for this node, not the whole scene.
    # Only the requested page is inspected/evaluated. Stable instance-name order.
    matched = sorted(node.globParms(view.get("pattern", "*"), single_pattern=True), key=lambda parm: parm.name())
    offset, limit = view.get("offset", 0), view.get("limit", 64)
    records = []
    for parm in matched[offset:offset + limit]:
        template = parm.parmTemplate()
        multipart = parm.isMultiParmInstance()
        record = {**parameter_template(template, redact), "name": parm.name(),
                        "name_kind": "runtime_instance", "tuple_name": optional_call(optional_call(parm, "tuple"), "name"),
                        "component_index": optional_call(parm, "componentIndex"),
                        "multiparm_instance": multipart,
                        "multiparm_indices": list(parm.multiParmInstanceIndices()) if multipart else [],
                        "value_status": "not_requested"}
        if view.get("include_values", False):
            try:
                record.update(value=bounded_value(parm.eval(), redact), value_status="ok")
            except Exception as exc:
                if strict:
                    raise
                record.update(value_status="error", error={"code": "PARAMETER_EVALUATION_FAILED",
                              "message": redact(str(exc))[:512], "parameter": parm.name(),
                              "index": offset + len(records), "path": view.get("path", "/obj")})
        records.append(record)
    end = offset + len(records)
    return {"parameters": records, "total": len(matched), "offset": offset,
            "next_offset": end if end < len(matched) else None, "truncated": end < len(matched),
            "include_values": view.get("include_values", False),
            "status": "partial" if any(r["value_status"] == "error" for r in records) else "ok"}


def geometry_facts(node, view, redact=lambda text: text):
    geometry = node.geometry()  # This targeted view may cook the requested node.
    counts = {"point": int(geometry.intrinsicValue("pointcount")),
              "primitive": int(geometry.intrinsicValue("primitivecount")),
              "vertex": int(geometry.intrinsicValue("vertexcount")), "detail": 1}
    bounds = geometry.boundingBox()
    result = {"points": counts["point"], "primitives": counts["primitive"], "vertices": counts["vertex"],
              "bounds": {"min": list(bounds.minvec()), "max": list(bounds.maxvec())},
              "attributes": {}, "samples": {}, "truncated_attributes": {}, "missing_attributes": {}}
    space = optional_call(node, "parent")
    for _ in range(32):
        if space is None or optional_call(optional_call(optional_call(space, "type"), "category"), "name") == "Object":
            break
        space = optional_call(space, "parent")
    else:
        space = None
    is_sop = optional_call(optional_call(optional_call(node, "type"), "category"), "name") == "Sop"
    result["bounds"].update(space="object_local" if is_sop and space is not None else "unknown",
                            space_path=optional_call(space, "path") if is_sop else None,
                            node_path=optional_call(node, "path"), world_transform_applied=False,
                            requires_space_conversion=True)
    if view.get("include_groups", False):
        result["groups"] = {}
        limit = view.get("group_limit", 32)
        for owner, method in (("point", "pointGroups"), ("primitive", "primGroups"), ("edge", "edgeGroups")):
            groups = optional_call(geometry, method)
            groups = sorted(groups, key=lambda group: group.name()) if groups is not None else None
            result["groups"][owner] = {"available": groups is not None,
                "names": [g.name() for g in groups[:limit]] if groups is not None else None,
                "total": len(groups) if groups is not None else None,
                "truncated": len(groups) > limit if groups is not None else None}
    names, sample_count = view.get("attributes"), view.get("samples", 0)
    for owner in view.get("owners", ["point", "primitive"]):
        prefix = {"point": "Point", "primitive": "Prim", "vertex": "Vertex", "detail": "Global"}[owner]
        if names:
            found = [(name, getattr(geometry, "find" + prefix + "Attrib")(name)) for name in names]
            attributes = [attribute for _, attribute in found if attribute is not None]
            result["missing_attributes"][owner] = [name for name, attribute in found if attribute is None]
        else:
            attributes = getattr(geometry, prefix[0].lower() + prefix[1:] + "Attribs")()
        result["truncated_attributes"][owner] = len(attributes) > 64
        selected = attributes[:64]
        records = [{"name": a.name(), "owner": owner, "data_type": str(a.dataType()),
                    "tuple_size": a.size(), "qualifier": a.qualifier(), "is_array": a.isArrayType()}
                   for a in selected]
        result["attributes"][owner] = records
        if owner in {"point", "primitive"}:
            result[owner + "_attributes"] = [record["name"] for record in records]
        if not sample_count:
            continue
        # Random access avoids constructing geometry.points()/prims()/vertices().
        # Native arrays/dictionaries are deliberately metadata-only: their single
        # value can itself be unbounded even when the element count is limited.
        samples = []
        for index in range(min(sample_count, counts[owner])):
            element = geometry if owner == "detail" else getattr(
                geometry, {"point": "point", "primitive": "prim", "vertex": "vertex"}[owner])(index)
            values = {}
            for attribute, record in zip(selected[:16], records[:16]):
                if record["is_array"] or record["tuple_size"] > 16 or "dict" in record["data_type"].lower():
                    values[record["name"]] = {"omitted": "Array, dictionary or oversized tuple; metadata only"}
                else:
                    values[record["name"]] = bounded_value(element.attribValue(attribute), redact)
            samples.append({"index": index, "values": values})
        result["samples"][owner] = {"elements": samples, "element_limit": sample_count,
                                   "attribute_limit": 16, "truncated": counts[owner] > len(samples)}
    return result
