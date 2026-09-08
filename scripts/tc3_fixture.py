"""Write-once TC3-A1 inputs; no generated walkway/HDA and no model execution."""
import json
import math
from pathlib import Path
import sys

import hou

from tc1_fixture import finish, inspect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".runtime/reviews/tc3/fixture"


def create():
    assert ROOT / ".runtime" in Path(hou.homeHoudiniDirectory()).resolve().parents
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "source.hip").exists():
        raise RuntimeError("Preserve the original fixture; run acceptance on separate copies")
    hou.hipFile.clear(suppress_save_prompt=True)
    for index in (1, 2):
        obj = hou.node("/obj").createNode("geo", f"road_guide_{index}", run_init_scripts=False)
        obj.parmTuple("t").set((3, 0.5, -2) if index == 1 else (-2, 0, 8))
        obj.parm("ry").set(12 if index == 1 else -16)
        geo = hou.Geometry()
        curve = geo.createPolygon(is_closed=False)
        for i in range(49):
            t = i / 48
            position = ((22 * t, 0.8 * t, 2.5 * math.sin(math.pi * t)) if index == 1 else
                        (14 * t, 2 * t * t, 3 * math.sin(1.7 * math.pi * t)))
            point = geo.createPoint()
            point.setPosition(position)
            curve.addVertex(point)
        source = obj.createNode("stash", "existing_curve")
        source.parm("stash").set(geo)
        edit = obj.createNode("edit", "artist_adjustment")
        edit.setInput(0, source)
        finish(edit)
        obj.layoutChildren()
    for name, size in (("paving_module_a", (0.6, 0.12, 1.0)), ("paving_module_b", (0.3, 0.16, 1.0)),
                       ("curb_module", (0.9, 0.22, 0.18))):
        obj = hou.node("/obj").createNode("geo", name, run_init_scripts=False)
        node = obj.createNode("box", "existing_module")
        node.parmTuple("size").set(size)
        finish(node)
        obj.setDisplayFlag(False)
    for index in (1, 2):
        guide = hou.node(f"/obj/road_guide_{index}")
        center = guide.displayNode().geometry().points()[23].position() * guide.worldTransform()
        obj = hou.node("/obj").createNode("geo", f"exclusion_area_{index}", run_init_scripts=False)
        obj.parmTuple("t").set(tuple(center))
        obj.parm("ry").set(guide.evalParm("ry"))
        box = obj.createNode("box", "existing_exclusion")
        box.parmTuple("size").set((2, 5, 5))
        finish(box)
        obj.setDisplayFlag(False)
    keep = hou.node("/obj").createNode("geo", "unrelated_keep_asset", run_init_scripts=False)
    keep.parmTuple("t").set((-3, 1, -4))
    finish(keep.createNode("box", "existing_asset"))
    hou.node("/obj/road_guide_1").setSelected(True, clear_all_selected=True)
    hou.node("/obj").layoutChildren()
    hou.setFrame(1)
    hou.hipFile.save(str(OUT / "source.hip"))
    report = inspect()
    assert not report["node_errors"], report["node_errors"]
    report.update(model_run=False, target_generator_present=False)
    (OUT / "source-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"fixture": str(OUT / "source.hip"), "verified_nodes": len(report["nodes"])}))


def move_inputs():
    """Explicit tester action after turn one, not part of the model's workflow."""
    assert ROOT / ".runtime/reviews/tc3" in Path(hou.hipFile.path()).resolve().parents
    edit = hou.node("/obj/road_guide_1/artist_adjustment")
    exclusion = hou.node("/obj/exclusion_area_1")
    if edit is None or exclusion is None:
        raise RuntimeError("Original input was not preserved; record this instead of repairing the model output")
    before = {"curve_group": edit.evalParm("group"), "curve_delta": list(edit.parmTuple("t").eval()),
              "exclusion_t": list(exclusion.parmTuple("t").eval())}
    edit.parm("group").set("20-28")
    edit.parmTuple("t").set((0, 0, 0.5))
    exclusion.parm("tx").set(before["exclusion_t"][0] + 0.8)
    return {"tester_action": True, "before": before, "point_group": "20-28", "curve_delta": [0, 0, 0.5],
            "exclusion_t": list(exclusion.parmTuple("t").eval())}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        hou.hipFile.load(str(OUT / "source.hip"), suppress_save_prompt=True)
        report = inspect()
        assert not report["node_errors"], report["node_errors"]
        (OUT / "fresh-load-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"fresh_load_cook": "passed", "verified_nodes": len(report["nodes"])}))
    else:
        create()
