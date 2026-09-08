"""Create/inspect the dedicated TC-1 fixture in hython; never open a user HIP.

Run with H22 hython and isolated HOUDINI_USER_PREF_DIR containing __HVER__.
Outputs are restricted to this checkout's .runtime/reviews/tc1/fixture.
The authoring model receives only the HIP and the natural-language task.
"""
import json
import math
from pathlib import Path
import sys

import hou

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".runtime" / "reviews" / "tc1" / "fixture"


def center(t):
    return (22 * t, 0.88 * t + 0.28 * math.sin(1.6 * math.pi * t),
            2.4 * math.sin(math.pi * t) + 0.8 * math.sin(2 * math.pi * t))


def curve_geometry():
    geo = hou.Geometry()
    poly = geo.createPolygon(is_closed=False)
    for i in range(49):
        x, y, z = center(i / 48)
        point = geo.createPoint()
        point.setPosition((x, y, z + 1.25))
        poly.addVertex(point)
    return geo


def walkway_geometry():
    geo, rows = hou.Geometry(), []
    for i in range(97):
        x, y, z = center(i / 96)
        row = []
        for offset in (-1.8, 1.8):
            point = geo.createPoint()
            point.setPosition((x, y, z + offset))
            row.append(point)
        rows.append(row)
    for left, right in zip(rows, rows[1:]):
        quad = geo.createPolygon()
        for point in (left[0], left[1], right[1], right[0]):
            quad.addVertex(point)
    return geo


def finish(node):
    node.setDisplayFlag(True)
    node.setRenderFlag(True)
    return node


def geo_object(name, transformed=False):
    obj = hou.node("/obj").createNode("geo", name, run_init_scripts=False)
    if transformed:
        obj.parmTuple("t").set((3.0, 0.5, -2.0))
        obj.parmTuple("r").set((0.0, 12.0, 0.0))
    return obj


def create():
    OUT.mkdir(parents=True, exist_ok=True)
    assert ROOT / ".runtime" in Path(hou.homeHoudiniDirectory()).resolve().parents
    if (OUT / "source.hip").exists():
        raise RuntimeError("Fixture already exists; preserve it and use the recorded source")
    hou.hipFile.clear(suppress_save_prompt=True)
    walkway = geo_object("walkway", True)
    source = walkway.createNode("stash", "existing_surface")
    source.parm("stash").set(walkway_geometry())
    finish(source)
    guide = geo_object("guide_curve", True)
    source = guide.createNode("stash", "existing_curve")
    source.parm("stash").set(curve_geometry())
    edit = guide.createNode("edit", "artist_adjustment")
    edit.setInput(0, source)
    finish(edit)
    for name, color, width in (("post_module_a", (0.3, 0.16, 0.08), 0.14),
                                ("post_module_b", (0.34, 0.4, 0.48), 0.2)):
        obj = geo_object(name)
        controls = obj.parmTemplateGroup()
        controls.append(hou.FloatParmTemplate("post_height", "Post Height", 1, default_value=(1.0,)))
        controls.append(hou.FloatParmTemplate("post_width", "Post Width", 1, default_value=(width,)))
        controls.append(hou.FolderParmTemplate("accents", "Accents", parm_templates=(
            hou.FloatParmTemplate("accent_height#", "Accent Height", 1, default_value=(0.8,)),),
            folder_type=hou.folderType.MultiparmBlock))
        obj.setParmTemplateGroup(controls)
        obj.parm("accents").set(2)
        obj.parm("accent_height2").set(0.95)
        shaft = obj.createNode("box", "shaft")
        for parm, expression in (("sizey", 'ch("../post_height")'), ("ty", 'ch("../post_height")/2'),
                                 ("sizex", 'ch("../post_width")'), ("sizez", 'ch("../post_width")')):
            shaft.parm(parm).setExpression(expression)
        cap = obj.createNode("box", "cap")
        cap.parmTuple("size").set((width * 1.45, 0.07, width * 1.45))
        cap.parm("ty").setExpression('ch("../post_height") - 0.035')
        merge = obj.createNode("merge", "module_geometry")
        merge.setInput(0, shaft)
        merge.setInput(1, cap)
        finish(merge)
        obj.setDisplayFlag(False)
        mat = hou.node("/mat").createNode("principledshader::2.0", name + "_material")
        mat.parmTuple("basecolor").set(color)
        obj.parm("shop_materialpath").set(mat.path())
        obj.layoutChildren()
    retained = geo_object("unrelated_keep_asset")
    retained.parmTuple("t").set((18.0, 0.5, -5.0))
    sculpture = retained.createNode("box", "existing_sculpture")
    sculpture.parmTuple("size").set((0.8, 2.5, 0.8))
    sculpture.parm("ty").set(1.25)
    finish(sculpture)
    camera = hou.node("/obj").createNode("cam", "existing_camera")
    eye, target = hou.Vector3(28, 17, 28), hou.Vector3(13, 1, -1)
    z = (eye - target).normalized()
    x = hou.Vector3(0, 1, 0).cross(z).normalized()
    y = z.cross(x)
    camera.setWorldTransform(hou.Matrix4((*x, 0, *y, 0, *z, 0, *eye, 1)))
    camera.parm("focal").set(42)
    marker = geo_object("opening_location")
    point = hou.Geometry()
    local = hou.Vector3(*center(0.64)) + hou.Vector3(0, 0, 1.25)
    point.createPoint().setPosition(local * guide.worldTransform())
    stash = marker.createNode("stash", "location")
    stash.parm("stash").set(point)
    finish(stash)
    marker.setDisplayFlag(False)
    guide.setSelected(True, clear_all_selected=True)
    hou.node("/obj").layoutChildren()
    hou.hipFile.save(str(OUT / "source.hip"))
    report = inspect()
    assert not report["node_errors"], report["node_errors"]
    (OUT / "source-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"fixture": str(OUT / "source.hip"), "verified_nodes": len(report["nodes"])}))


def move_curve():
    """Tester action between the two turns, through the existing runtime queue."""
    edit = hou.node("/obj/guide_curve/artist_adjustment")
    edit.parm("group").set("29-36")
    edit.parmTuple("t").set((0.0, 0.0, -0.5))
    hou.node("/obj/opening_location").setSelected(True, clear_all_selected=True)
    return {"edited_node": edit.path(), "point_group": edit.parm("group").eval(),
            "delta": list(edit.parmTuple("t").eval()), "selected_marker": "/obj/opening_location"}


def inspect():
    nodes, errors = [], {}
    for node in hou.node("/obj").allSubChildren():
        item = {"path": node.path(), "type": node.type().name(),
                "inputs": [n.path() if n else None for n in node.inputs()]}
        if isinstance(node, hou.SopNode):
            geo = node.geometry()
            item.update(points=geo.intrinsicValue("pointcount"), primitives=geo.intrinsicValue("primitivecount"),
                        bounds=list(geo.boundingBox().minvec()) + list(geo.boundingBox().maxvec()))
            if node.errors():
                errors[node.path()] = list(node.errors())
        if isinstance(node, hou.ObjNode):
            item["transform"] = list(node.worldTransform().asTuple())
            item["material"] = node.evalParm("shop_materialpath") if node.parm("shop_materialpath") else None
        nodes.append(item)
    return {"houdini_version": hou.applicationVersionString(), "nodes": nodes, "node_errors": errors,
            "materials": [n.path() for n in hou.node("/mat").children()]}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        hou.hipFile.load(str(OUT / "source.hip"), suppress_save_prompt=True)
        report = inspect()
        assert not report["node_errors"], report["node_errors"]
        print(json.dumps({"fresh_load_cook": "passed", "verified_nodes": len(report["nodes"])}))
    else:
        create()
