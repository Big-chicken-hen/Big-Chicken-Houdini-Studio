"""Environment selection and owned process lifecycle; no knowledge or recovery planner."""
from __future__ import annotations

import contextlib
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .codex.protocol import SUPPORTED_CODEX_VERSION
from .common import AppPaths, StudioError, atomic_json, new_id, read_json
from .ownership import WorkspaceLock, execution_lock
from .workspace import Workspaces


def hidden_flags():
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def console_python(executable=None):
    """pythonw has no standard streams; helpers and MCP always need console Python."""
    path = Path(executable or sys.executable).absolute()
    if path.name.lower() == "pythonw.exe":
        path = path.with_name("python.exe")
    if not path.is_file():
        raise StudioError("PYTHON_REQUIRED", "Console Python is missing; run Setup Studio.cmd again")
    return str(path)


def render_output_directory(paths):
    """Legacy advanced override only; ordinary output is resolved in the scene."""
    value = os.environ.get("HIA_RENDER_OUTPUT_DIR")
    if not value:
        return None
    path = Path(value)
    return (path if path.is_absolute() else paths.root / path).resolve()


def storage_environment(paths):
    """Child/process-local storage settings; never edit a user's global configuration."""
    directories = {"CODEX_HOME": paths.codex_home, "TEMP": paths.cache("tmp"),
                   "TMP": paths.cache("tmp"), "TMPDIR": paths.cache("tmp"),
                   "PIP_CACHE_DIR": paths.cache("pip"), "XDG_CACHE_HOME": paths.cache_root,
                   "XDG_CONFIG_HOME": paths.data("config"), "XDG_DATA_HOME": paths.data("data")}
    for path in directories.values():
        path.mkdir(parents=True, exist_ok=True)
    return {**{key: str(value) for key, value in directories.items()},
            "HIA_PROJECT_ROOT": str(paths.root), "BCS_DATA_ROOT": str(paths.data_root),
            "BCS_CACHE_ROOT": str(paths.cache_root), "PYTHONPATH": str(paths.install("src")),
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
            "PIP_CONFIG_FILE": os.devnull, "PIP_DISABLE_PIP_VERSION_CHECK": "1"}


def helper_environment(paths):
    env = dict(os.environ)
    for name in list(env):
        if name.startswith(("HIA_", "FXHOUDINIMCP_", "BCS_", "HOUDINI_", "QT_", "PYSIDE")):
            env.pop(name)
    for name in ("PYTHONHOME", "PYTHONUSERBASE", "PYTHONPYCACHEPREFIX", "HFS", "HB", "HH", "HHP",
                 "PIP_TARGET", "PIP_PREFIX", "PIP_ROOT", "PIP_USER"):
        env.pop(name, None)
    env.update(storage_environment(paths))
    output_override = render_output_directory(paths)
    if output_override is not None:
        env["HIA_RENDER_OUTPUT_DIR"] = str(output_override)
    return env


def discover_houdini():
    roots = []
    if os.environ.get("HFS"):
        roots.append(Path(os.environ["HFS"]))
    if os.environ.get("ProgramFiles"):
        base = Path(os.environ["ProgramFiles"]) / "Side Effects Software"
        if base.exists():
            roots.extend(base.glob("Houdini *"))
    values = []
    for root in roots:
        executable = root / "bin" / ("houdini.exe" if os.name == "nt" else "houdini")
        if executable.is_file() and not any(item["path"] == str(executable) for item in values):
            values.append({"label": root.name, "path": str(executable)})
    return sorted(values, key=lambda item: tuple(int(x) for x in re.findall(r"\d+", item["label"])), reverse=True)


def codex_executable(paths):
    name = "codex.exe" if os.name == "nt" else "codex"
    candidates = [os.environ.get("BCS_CODEX_PATH"), paths.local("toolchains", "codex", name), shutil.which(name)]
    for value in candidates:
        if value and Path(value).is_file():
            return str(Path(value).resolve())
    return ""


def check_codex(codex, paths=None):
    paths = paths or AppPaths()
    if not codex or not Path(codex).is_file():
        raise StudioError("CODEX_REQUIRED", "Select an installed Codex executable")
    if os.name == "nt" and Path(codex).suffix.lower() != ".exe":
        raise StudioError("CODEX_REQUIRED", "Select the native codex.exe, not an npm shell wrapper")
    try:
        result = subprocess.run([str(Path(codex).resolve()), "--version"], capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=8,
                                cwd=paths.root, env=helper_environment(paths),
                                creationflags=hidden_flags(), check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise StudioError("CODEX_UNAVAILABLE", "Could not read the selected Codex version") from exc
    if result.stdout.strip() != "codex-cli " + SUPPORTED_CODEX_VERSION:
        raise StudioError("CODEX_VERSION_UNTESTED", "This release requires Codex " + SUPPORTED_CODEX_VERSION +
                          "; select that version or update the protocol contract and smoke checks")
    return str(Path(codex).resolve())


def preflight(houdini, codex, paths=None):
    if not Path(houdini).is_file() or Path(houdini).name.lower() not in {"houdini.exe", "houdini", "houdinifx.exe"}:
        raise StudioError("HOUDINI_REQUIRED", "Select a Houdini GUI executable")
    return {"houdini": str(Path(houdini).resolve()), "codex": check_codex(codex, paths),
            "codex_version": SUPPORTED_CODEX_VERSION}


def child_environment(paths, workspace_id, session_id, token):
    folder = paths.session(session_id)
    for path in (folder, paths.cache("tmp"), paths.data("houdini-prefs")):
        path.mkdir(parents=True, exist_ok=True)
    env = helper_environment(paths)
    env.update({"HIA_PROJECT_ROOT": str(paths.root), "BCS_WORKSPACE_ID": workspace_id,
                "BCS_SESSION_ID": session_id, "BCS_SESSION_TOKEN": token, "BCS_AUTOSTART": "1",
                "PYTHONPATH": str(paths.root / "src"), "HOUDINI_PACKAGE_DIR": str(paths.root / "houdini" / "packages"),
                "HOUDINI_USER_PREF_DIR": str(paths.data("houdini-prefs", "__HVER__")),
                "HOUDINI_TEMP_DIR": str(paths.cache("tmp")), "TEMP": str(paths.cache("tmp")),
                "TMP": str(paths.cache("tmp")), "PYTHONDONTWRITEBYTECODE": "1",
                "BCS_PYTHON_EXECUTABLE": console_python()})
    return env


def launch(paths, workspace_id, houdini, codex, hip=None):
    Workspaces(paths).get(workspace_id)
    checked = preflight(houdini, codex, paths)
    if hip and (not Path(hip).is_file() or Path(hip).suffix.lower() not in {".hip", ".hiplc", ".hipnc"}):
        raise StudioError("HIP_INVALID", "Select an existing Houdini scene")
    session_id, token = new_id(), secrets.token_urlsafe(48)
    folder = paths.session(session_id)
    folder.mkdir(parents=True, exist_ok=False)
    env = child_environment(paths, workspace_id, session_id, token)
    output = env.get("HIA_RENDER_OUTPUT_DIR")
    atomic_json(folder / "launch.json", {**checked, "workspace_id": workspace_id,
                "launcher_session_id": session_id, "hip": str(Path(hip).resolve()) if hip else None,
                "render_output_directory": output})
    atomic_json(folder / "status.json", {"state": "starting", "render_output_directory": output})
    try:
        with (folder / "supervisor.log").open("ab") as log:
            process = subprocess.Popen([env["BCS_PYTHON_EXECUTABLE"], "-m", "studio", "supervise",
                                        "--session", session_id],
                                       cwd=paths.root, env=env, stdout=log, stderr=log,
                                       stdin=subprocess.DEVNULL, creationflags=hidden_flags())
    except OSError as exc:
        atomic_json(folder / "status.json", {"state": "failed", "message": "Supervisor could not start",
                                            "render_output_directory": output})
        raise StudioError("LAUNCH_FAILED", "Supervisor could not start; run setup and check the Python selection") from exc
    return {"session_id": session_id, "supervisor_pid": process.pid, "directory": str(folder),
            "render_output_directory": output}


def supervise(paths, session_id):
    from .bridge import Bridge

    folder = paths.session(session_id)
    lock = None
    bridge = None
    process = None
    token = os.environ.get("BCS_SESSION_TOKEN", "")
    status = {"supervisor_pid": os.getpid()}
    try:
        config = read_json(folder / "launch.json")
        if (not token or os.environ.get("BCS_SESSION_ID") != session_id or
                config.get("launcher_session_id") != session_id or
                os.environ.get("BCS_WORKSPACE_ID") != config.get("workspace_id")):
            raise StudioError("SESSION_ENV_REQUIRED", "Supervisor requires the fresh environment from the launcher")
        Workspaces(paths).get(config["workspace_id"])
        lock = WorkspaceLock(paths.workspace(config["workspace_id"]) / "session.lock")
        # Avoid opening another GUI while an orphaned runtime still owns execution.
        # This probe is advisory; the runtime acquires its own lock before Ledger.
        execution_lock(paths, config["workspace_id"]).close()
        bridge = Bridge(paths, config["workspace_id"], session_id, token, config["codex"])
        bridge.start()
        command = [config["houdini"]] + ([config["hip"]] if config.get("hip") else [])
        with (folder / "houdini.log").open("ab") as log:
            process = subprocess.Popen(command, env=dict(os.environ),
                                       cwd=paths.workspace(config["workspace_id"]) / "work",
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=log)
            status["houdini_pid"] = process.pid
            atomic_json(folder / "status.json", {**status, "state": "starting"})
            while process.poll() is None:
                if (folder / "runtime-error.json").is_file():
                    failure = read_json(folder / "runtime-error.json")
                    if (failure.get("launcher_session_id") == session_id and
                            failure.get("workspace_id") == config["workspace_id"]):
                        raise StudioError("RUNTIME_START_FAILED", failure["error"]["message"], 503)
                if (folder / "runtime.json").is_file():
                    descriptor = read_json(folder / "runtime.json")
                    if (descriptor.get("launcher_session_id") == session_id and
                            descriptor.get("workspace_id") == config["workspace_id"] and
                            descriptor.get("houdini_pid") == process.pid):
                        # Connection registration only; no claim about a scene operation completing.
                        atomic_json(folder / "status.json", {**status, "state": "ready"})
                        break
                time.sleep(0.25)
            process.wait()
            atomic_json(folder / "status.json", {**status, "state": "closed", "returncode": process.returncode,
                                                "message": "Houdini exited; consult operation receipts for scene outcomes"})
            return process.returncode or 0
    except (Exception, KeyboardInterrupt) as exc:
        message = str(exc) if isinstance(exc, StudioError) else "Supervisor failed; scene operation outcomes are unconfirmed"
        if token:
            message = message.replace(token, "[redacted]")
        alive = process is not None and process.poll() is None
        atomic_json(folder / "status.json", {**status, "state": "failed", "message": message[:1000],
                                            "houdini_left_running": alive})
        return 1
    finally:
        if bridge:
            with contextlib.suppress(Exception):
                bridge.close()
        if lock:
            # If supervision failed after opening the GUI, retain workspace
            # ownership until that GUI exits. Never kill it or permit a second
            # session to reuse the workspace while it is still running.
            if process is not None and process.returncode is None:
                with contextlib.suppress(Exception):
                    process.wait()
            lock.close()
