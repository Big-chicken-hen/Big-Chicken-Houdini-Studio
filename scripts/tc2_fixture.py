"""Prepare the TC2-A1 input, not a completed blind or a model-run result.

Run with H22 hython and checkout-local preferences containing __HVER__.
The source is write-once; model runs use separate copies under the TC-2 review.
"""
import json
from pathlib import Path
import sys

import hou

from tc1_fixture import finish, inspect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".runtime" / "reviews" / "tc2" / "fixture"


def create():
    assert ROOT / ".runtime" in Path(hou.homeHoudiniDirectory()).resolve().parents
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "source.hip").exists():
        raise RuntimeError("Preserve the existing source; use a separate acceptance copy")
    hou.hipFile.clear(suppress_save_prompt=True)
    parent = hou.node("/obj").createNode("subnet", "window_assembly")
    parent.parmTuple("t").set((4, 0.4, -2))
    parent.parmTuple("r").set((0, 18, 0))
    parent.parmTuple("s").set((1.1, 1, 0.9))
    opening = parent.createNode("geo", "window_opening", run_init_scripts=False)
    shape = hou.Geometry()
    boundary = shape.createPolygon()
    for position in ((-1.5, 0.5, 0), (1.5, 0.5, 0), (1.5, 2.5, 0), (-1.5, 2.5, 0)):
        point = shape.createPoint()
        point.setPosition(position)
        boundary.addVertex(point)
    source = opening.createNode("stash", "opening_boundary")
    source.parm("stash").set(shape)
    finish(source)
    opening.setDisplayFlag(False)
    frame = parent.createNode("geo", "existing_window_frame", run_init_scripts=False)
    merge = frame.createNode("merge", "OUT_FRAME")
    for i, (name, size, position) in enumerate((
        ("left", (0.14, 2.28, 0.22), (-1.57, 1.5, 0)),
        ("right", (0.14, 2.28, 0.22), (1.57, 1.5, 0)),
        ("bottom", (3, 0.14, 0.22), (0, 0.43, 0)),
        ("top", (3, 0.14, 0.22), (0, 2.57, 0)),
    )):
        node = frame.createNode("box", name)
        node.parmTuple("size").set(size)
        node.parmTuple("t").set(position)
        merge.setInput(i, node)
    finish(merge)
    frame.layoutChildren()
    module = parent.createNode("geo", "existing_blade_module", run_init_scripts=False)
    blade = module.createNode("box", "blade_source")
    blade.parmTuple("size").set((2.72, 0.035, 0.18))
    finish(blade)
    module.setDisplayFlag(False)
    unrelated = hou.node("/obj").createNode("geo", "unrelated_keep_asset", run_init_scripts=False)
    unrelated.parmTuple("t").set((-3, 0.5, 1))
    box = unrelated.createNode("box", "existing_pedestal")
    box.parmTuple("size").set((0.6, 1, 0.6))
    finish(box)
    camera = hou.node("/obj").createNode("cam", "existing_camera")
    target = hou.Vector3(0, 1.5, 0) * parent.worldTransform()
    eye = target + hou.Vector3(6, 4, 7)
    z = (eye - target).normalized()
    x = hou.Vector3(0, 1, 0).cross(z).normalized()
    y = z.cross(x)
    camera.setWorldTransform(hou.Matrix4((*x, 0, *y, 0, *z, 0, *eye, 1)))
    camera.parm("focal").set(42)
    parent.layoutChildren()
    hou.node("/obj").layoutChildren()
    parent.setSelected(True, clear_all_selected=True)
    hou.setFrame(1)
    hou.hipFile.save(str(OUT / "source.hip"))
    report = inspect()
    assert not report["node_errors"], report["node_errors"]
    report.update(model_run=False, target_blind_network_present=False,
                  opening_local_extent=[-1.5, 0.5, 0, 1.5, 2.5, 0])
    (OUT / "source-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"fixture": str(OUT / "source.hip"), "verified_nodes": len(report["nodes"]),
                      "model_run": False}))


def move_parent():
    """Explicit tester action between model turns, through the production queue."""
    assert ROOT / ".runtime" / "reviews" / "tc2" in Path(hou.hipFile.path()).resolve().parents
    parent = hou.node("/obj/window_assembly")
    before = {"t": list(parent.parmTuple("t").eval()), "r": list(parent.parmTuple("r").eval())}
    parent.parmTuple("t").set(tuple(a + b for a, b in zip(before["t"], (0.8, 0.2, -0.6))))
    parent.parm("ry").set(before["r"][1] + 22)
    viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    viewport = viewer.curViewport()
    viewport.lockCameraToView(False)
    viewport.useDefaultCamera()
    viewport.frameBoundingBox(hou.BoundingBox(99, 0, 99, 101, 2, 101))
    return {"tester_action": True, "path": parent.path(), "before": before,
            "after": {"t": list(parent.parmTuple("t").eval()), "r": list(parent.parmTuple("r").eval())},
            "viewport_moved_away": True}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        hou.hipFile.load(str(OUT / "source.hip"), suppress_save_prompt=True)
        report = inspect()
        assert not report["node_errors"], report["node_errors"]
        (OUT / "fresh-load-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"fresh_load_cook": "passed", "verified_nodes": len(report["nodes"])}))
    else:
        create()
