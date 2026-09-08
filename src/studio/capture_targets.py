"""Small SOP/OBJ target framing adapter; no visibility or authoring mutations."""
from __future__ import annotations

import itertools
import math

from .common import StudioError
from .inspection import optional_bool, optional_call


def object_owner(node):
    for _ in range(64):
        if node is None:
            break
        if node.type().category().name() == "Object":
            return node
        node = node.parent()
    raise StudioError("REVIEW_SPACE_UNSUPPORTED", "Cannot establish the SOP object's coordinate space")


def viewer_space(viewer):
    pwd = viewer.pwd()
    category = optional_call(optional_call(pwd, "childTypeCategory"), "name")
    # H22 GUI verifies world framing at OBJ and SOP level when this native flag
    # is false. Local-world mode is explicit unsupported, never guessed as world.
    local = optional_bool(viewer, "isWorldSpaceLocal")
    if category not in {"Object", "Sop"} or local is not False:
        raise StudioError("REVIEW_SPACE_UNSUPPORTED", "Review requires a confirmed world-space OBJ/SOP viewer")
    return {"space": "world", "viewer_path": pwd.path(), "viewer_child_category": category,
            "is_world_space_local": local, "source": "SceneViewer.isWorldSpaceLocal"}


def transformed_bounds(hou, bounds, transform):
    values = list(bounds.minvec()) + list(bounds.maxvec())
    if len(values) != 6 or not all(math.isfinite(v) for v in values) or any(values[i] > values[i + 3] for i in range(3)):
        raise StudioError("REVIEW_BOUNDS_UNAVAILABLE", "Target has invalid geometry bounds")
    corners = [hou.Vector3(corner) * transform for corner in itertools.product(
        *[(values[i], values[i + 3]) for i in range(3)])]
    result = [min(p[i] for p in corners) for i in range(3)] + [max(p[i] for p in corners) for i in range(3)]
    if not all(math.isfinite(v) for v in result):
        raise StudioError("REVIEW_BOUNDS_UNAVAILABLE", "Target transform does not produce finite bounds")
    return values, result


def resolve_targets(hou, viewer, target):
    space = viewer_space(viewer)
    paths = target.get("paths")
    if paths is None:
        paths = [node.path() for node in hou.selectedNodes()]
    if not 1 <= len(paths) <= 8:
        raise StudioError("REVIEW_TARGET_COUNT", "Select or supply one to eight SOP/OBJ geometry nodes")
    records, warnings = [], []
    for path in dict.fromkeys(paths):
        node = hou.node(path)
        if node is None:
            raise StudioError("REVIEW_TARGET_MISSING", "Capture target does not exist", target_path=path)
        category = node.type().category().name()
        if category == "Sop":
            source, owner = node, object_owner(node)
        elif category == "Object" and optional_call(optional_call(node, "childTypeCategory"), "name") == "Sop":
            owner, source = node, node.displayNode()
        else:
            raise StudioError("REVIEW_TARGET_UNSUPPORTED", "Capture supports SOP geometry or an OBJ with a display SOP", target_path=path)
        if source is None or source.type().category().name() != "Sop":
            raise StudioError("REVIEW_DISPLAY_SOURCE_MISSING", "Object has no supported display SOP", target_path=path)
        geometry = source.geometry()  # Requested frame has already been established.
        if int(geometry.intrinsicValue("pointcount")) <= 0:
            raise StudioError("REVIEW_EMPTY_GEOMETRY", "Capture target geometry is empty", target_path=path)
        local, world = transformed_bounds(hou, geometry.boundingBox(), owner.worldTransform())
        display = owner.displayNode()
        display_path = display.path() if display is not None else None
        if source.path() != display_path:
            warnings.append({"code": "TARGET_NOT_DISPLAY_OUTPUT", "path": path,
                             "display_source": display_path})
        records.append({"path": path, "geometry_source": source.path(), "object_path": owner.path(),
                        "local_bounds": local, "source_space": "object_local", "source_space_path": owner.path(),
                        "framing_bounds": world, "destination_space": "world", "display_source": display_path,
                        "object_display_flag": optional_bool(owner, "isDisplayFlagSet")})
    bounds = [min(r["framing_bounds"][i] for r in records) for i in range(3)] + [
        max(r["framing_bounds"][i + 3] for r in records) for i in range(3)]
    if all(bounds[i] == bounds[i + 3] for i in range(3)):
        raise StudioError("REVIEW_DEGENERATE_BOUNDS", "Target bounds have no framing extent")
    return {"requested": target, "resolved_paths": [r["path"] for r in records], "nodes": records,
            "bounds": bounds, "destination": space, "sample_frame": float(hou.frame()),
            "warnings": warnings, "visibility_verified": False, "policy": "framing_only_no_isolation"}


def named_view(hou, viewport, name):
    if viewport.type() != hou.geometryViewportType.Perspective:
        raise StudioError("REVIEW_VIEW_UNSUPPORTED", "Named review views require a freely orientable perspective viewport")
    z, up = {"front": ((0, 0, 1), (0, 1, 0)), "right": ((1, 0, 0), (0, 1, 0)),
             "top": ((0, 1, 0), (0, 0, -1)), "three_quarter": ((1, 0.65, 1), (0, 1, 0))}[name]
    z = hou.Vector3(z).normalized()
    x = hou.Vector3(up).cross(z).normalized()
    y = z.cross(x)
    camera = viewport.defaultCamera().stash()
    camera.setPerspective(name == "three_quarter")
    # GeometryViewportCamera.rotation is world-to-camera (transpose of the
    # rotation rows of viewTransform); this convention is verified in H22 GUI.
    camera.setRotation(hou.Matrix3([x[0], y[0], z[0], x[1], y[1], z[1], x[2], y[2], z[2]]))
    viewport.setDefaultCamera(camera)
    observed = viewport.viewTransform().asTuple()
    actual_z = hou.Vector3(observed[8:11]).normalized()
    perspective = bool(viewport.defaultCamera().isPerspective())
    if actual_z.dot(z) < 1 - 1e-6 or perspective != (name == "three_quarter"):
        raise StudioError("REVIEW_VIEW_UNSUPPORTED", "Native viewport did not establish the requested world-axis view")
    return {"name": name, "direction_space": "world", "direction": list(-actual_z),
            "projection": "perspective" if perspective else "orthographic"}
