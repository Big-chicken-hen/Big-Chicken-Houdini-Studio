"""Destination policy for new outputs, not an execution or completion service."""
from __future__ import annotations

from pathlib import Path

from .common import StudioError, inside
from .targets import path_key


def resolve_output(scene, temporary_root, kind, filename, *, explicit=None, existing=None, expand=str):
    folders = {"render": "renders", "export": "exports", "asset": "assets"}
    if kind not in folders:
        raise StudioError("OUTPUT_KIND_INVALID", "Use render, export or asset for a new output")
    # Existing node settings and explicit destinations are never rewritten to a
    # Studio default. Callers supply the complete output parameter/path here.
    for source, value in (("explicit", explicit), ("existing", existing)):
        if value is not None and str(value).strip():
            path = Path(expand(str(value))).expanduser().resolve()
            return {"kind": kind, "path": str(path), "source": source, "temporary": False}
    if not isinstance(filename, str) or not filename.strip():
        raise StudioError("OUTPUT_NAME_INVALID", "Supply a filename for the new output")
    filename = expand(filename)
    if filename in {".", ".."} or Path(filename).name != filename or any(c in filename for c in "/\\:"):
        raise StudioError("OUTPUT_NAME_INVALID", "Default output names must be filenames, not directory paths")
    saved = scene.get("saved_hip_path")
    if saved and path_key(saved) == path_key(scene.get("hip_path", "")):
        hip = Path(saved)
        base = hip.parent / "BigChickenStudio" / hip.stem / folders[kind]
        containment = hip.parent
        temporary, source = False, "hip"
    elif scene.get("is_new_file") is True:
        base = Path(temporary_root) / folders[kind]
        containment = Path(temporary_root)
        temporary, source = True, "temporary"
    else:
        raise StudioError("SCENE_FILE_STATE_UNKNOWN", "Save the current scene or choose an explicit output location")
    return {"kind": kind, "path": str(inside(base / filename, containment)), "source": source, "temporary": temporary}
