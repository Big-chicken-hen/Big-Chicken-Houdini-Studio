"""Targeted native parameter discovery and bounded geometry element samples."""
from __future__ import annotations

import math


def bounded_value(value):
    if isinstance(value, str):
        return value if len(value) <= 512 else {"text": value[:512], "truncated": True}
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, (tuple, list)) and len(value) <= 16:
        return [bounded_value(v) for v in value]
    return {"omitted": "Non-scalar or oversized value; use a targeted HOM read if needed"}


def parameter_instances(node, view):
    # HOM returns matching parameter handles for this node, not the whole scene.
    # Only the requested page's metadata is inspected; no parameter is evaluated.
    matched = node.globParms(view.get("pattern", "*"), single_pattern=True)
    offset, limit = view.get("offset", 0), view.get("limit", 64)
    records = []
    for parm in matched[offset:offset + limit]:
        template = parm.parmTemplate()
        multipart = parm.isMultiParmInstance()
        default = getattr(template, "defaultValue", None)
        records.append({"name": parm.name(), "template_name": template.name(),
                        "name_kind": "runtime_instance", "label": template.label(),
                        "type": str(template.type()), "components": template.numComponents(),
                        "multiparm_instance": multipart,
                        "multiparm_indices": list(parm.multiParmInstanceIndices()) if multipart else [],
                        "default": bounded_value(default()) if callable(default) else None})
    end = offset + len(records)
    return {"parameters": records, "total": len(matched), "offset": offset,
            "next_offset": end if end < len(matched) else None}


def geometry_facts(node, view):
    geometry = node.geometry()  # This targeted view may cook the requested node.
    counts = {"point": int(geometry.intrinsicValue("pointcount")),
              "primitive": int(geometry.intrinsicValue("primitivecount")),
              "vertex": int(geometry.intrinsicValue("vertexcount")), "detail": 1}
    bounds = geometry.boundingBox()
    result = {"points": counts["point"], "primitives": counts["primitive"], "vertices": counts["vertex"],
              "bounds": {"min": list(bounds.minvec()), "max": list(bounds.maxvec())},
              "attributes": {}, "samples": {}, "truncated_attributes": {}, "missing_attributes": {}}
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
                    "tuple_size": a.size(), "type_info": str(a.typeInfo()), "is_array": a.isArrayType()}
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
                    values[record["name"]] = bounded_value(element.attribValue(attribute))
            samples.append({"index": index, "values": values})
        result["samples"][owner] = {"elements": samples, "element_limit": sample_count,
                                   "attribute_limit": 16, "truncated": counts[owner] > len(samples)}
    return result
