"""Environment selection and owned process lifecycle; no knowledge or recovery planner."""
from __future__ import annotations

import contextlib
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .bridge import Bridge
from .codex.protocol import SUPPORTED_CODEX_VERSION
from .common import AppPaths, StudioError, atomic_json, new_id, read_json
from .workspace import Workspaces


def hidden_flags():
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def discover_houdini():
    roots = []
    if os.environ.get("HFS"):
        roots.append(Path(os.environ["HFS"]))
    base = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Side Effects Software"
    if base.exists():
        roots.extend(base.glob("Houdini *"))
    values = []
    for root in roots:
        executable = root / "bin" / ("houdini.exe" if os.name == "nt" else "houdini")
        if executable.is_file() and not any(item["path"] == str(executable) for item in values):
            values.append({"label": root.name, "path": str(executable)})
    return sorted(values, key=lambda item: tuple(int(x) for x in __import__("re").findall(r"\d+", item["label"])), reverse=True)


def codex_executable(paths):
    candidates = [paths.local("toolchains", "codex", "codex.exe"), os.environ.get("BCS_CODEX_PATH"), shutil.which("codex")]
    for value in candidates:
        if value and Path(value).is_file():
            return str(Path(value).resolve())
    return ""


def preflight(houdini, codex):
    if not Path(houdini).is_file() or Path(houdini).name.lower() not in {"houdini.exe", "houdini", "houdinifx.exe"}:
        raise StudioError("HOUDINI_REQUIRED", "Select a Houdini GUI executable")
    if not codex or not Path(codex).is_file():
        raise StudioError("CODEX_REQUIRED", "Select an installed Codex executable")
    result = subprocess.run([codex, "--version"], capture_output=True, text=True, timeout=8,
                            creationflags=hidden_flags(), check=True)
    if result.stdout.strip() != "codex-cli " + SUPPORTED_CODEX_VERSION:
        raise StudioError("CODEX_VERSION_UNTESTED", "This release is tested with Codex " + SUPPORTED_CODEX_VERSION +
                          "; select that version or update the protocol contract and smoke checks")
    return {"houdini": houdini, "codex": codex, "codex_version": SUPPORTED_CODEX_VERSION}


def child_environment(paths, workspace_id, session_id, token):
    folder = paths.session(session_id)
    for path in (folder, paths.local("tmp"), paths.local("houdini-prefs")):
        path.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    # No legacy HIA or fallback runtime is inherited into the new product.
    for name in list(env):
        if name.startswith(("HIA_", "FXHOUDINIMCP_", "BCS_")):
            env.pop(name)
    env.update({"HIA_PROJECT_ROOT": str(paths.root), "BCS_WORKSPACE_ID": workspace_id,
                "BCS_SESSION_ID": session_id, "BCS_SESSION_TOKEN": token, "BCS_AUTOSTART": "1",
                "PYTHONPATH": str(paths.root / "src"), "HOUDINI_PACKAGE_DIR": str(paths.root / "houdini" / "packages"),
                "HOUDINI_USER_PREF_DIR": str(paths.local("houdini-prefs", "__HVER__")),
                "HOUDINI_TEMP_DIR": str(paths.local("tmp")), "TEMP": str(paths.local("tmp")),
                "TMP": str(paths.local("tmp")), "PYTHONDONTWRITEBYTECODE": "1"})
    return env


def launch(paths, workspace_id, houdini, codex, hip=None):
    Workspaces(paths).get(workspace_id)
    checked = preflight(houdini, codex)
    if hip and (not Path(hip).is_file() or Path(hip).suffix.lower() not in {".hip", ".hiplc", ".hipnc"}):
        raise StudioError("HIP_INVALID", "Select an existing Houdini scene")
    session_id, token = new_id(), secrets.token_urlsafe(48)
    folder = paths.session(session_id)
    folder.mkdir(parents=True, exist_ok=False)
    atomic_json(folder / "launch.json", {**checked, "workspace_id": workspace_id,
                                        "launcher_session_id": session_id, "hip": hip})
    env = child_environment(paths, workspace_id, session_id, token)
    with (folder / "supervisor.log").open("ab") as log:
        process = subprocess.Popen([sys.executable, "-m", "studio", "supervise", "--session", session_id],
                                   cwd=paths.root, env=env, stdout=log, stderr=log,
                                   stdin=subprocess.DEVNULL, creationflags=hidden_flags())
    return {"session_id": session_id, "supervisor_pid": process.pid, "directory": str(folder)}


class WorkspaceLock:
    """One owned GUI session per workspace; lock release is handled by the OS on a crash."""
    def __init__(self, path):
        self.file = Path(path).open("a+b")
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise StudioError("WORKSPACE_IN_USE", "This workspace already has a running Studio session", 409) from exc

    def close(self):
        self.file.close()


def supervise(paths, session_id):
    folder = paths.session(session_id)
    config = read_json(folder / "launch.json")
    lock = None
    bridge = None
    try:
        lock = WorkspaceLock(paths.workspace(config["workspace_id"]) / "session.lock")
        bridge = Bridge(paths, config["workspace_id"], session_id, os.environ["BCS_SESSION_TOKEN"], config["codex"])
        bridge.start()
        command = [config["houdini"]] + ([config["hip"]] if config.get("hip") else [])
        with (folder / "houdini.log").open("ab") as log:
            process = subprocess.Popen(command, env=dict(os.environ),
                                       cwd=paths.workspace(config["workspace_id"]) / "work",
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=log)
            atomic_json(folder / "status.json", {"state": "starting", "houdini_pid": process.pid})
            while process.poll() is None:
                if (folder / "runtime.json").is_file():
                    atomic_json(folder / "status.json", {"state": "ready", "houdini_pid": process.pid})
                    break
                time.sleep(0.25)
            process.wait()
            atomic_json(folder / "status.json", {"state": "closed", "returncode": process.returncode})
    except Exception as exc:
        atomic_json(folder / "status.json", {"state": "failed", "message": str(exc)[:1000]})
    finally:
        if bridge:
            with contextlib.suppress(Exception):
                bridge.close()
        if lock:
            lock.close()
