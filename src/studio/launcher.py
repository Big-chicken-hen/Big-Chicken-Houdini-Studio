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
from .common import AppPaths, StudioError, atomic_json, identifier, new_id, read_json
from .ownership import WorkspaceLock, execution_lock
from .targets import SceneCatalog, SceneTarget, path_key
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


def codex_app_server_command(codex):
    """Use Windows' existing system proxy despite Studio's isolated CODEX_HOME."""
    command = [str(codex)]
    if os.name == "nt":
        command.extend(["--enable", "respect_system_proxy"])
    return [*command, "app-server"]


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
    """Explicit legacy workspace entrance; normal UI uses launch_target."""
    Workspaces(paths).get(workspace_id)
    checked = preflight(houdini, codex, paths)
    if hip and (not Path(hip).is_file() or Path(hip).suffix.lower() not in {".hip", ".hiplc", ".hipnc"}):
        raise StudioError("HIP_INVALID", "Select an existing Houdini scene")
    session_id = new_id()
    folder = paths.session(session_id)
    folder.mkdir(parents=True, exist_ok=False)
    return _spawn_session(paths, workspace_id, checked, hip, session_id)


def _spawn_session(paths, workspace_id, checked, hip, session_id, target=None):
    token = secrets.token_urlsafe(48)
    folder = paths.session(session_id)
    env = child_environment(paths, workspace_id, session_id, token)
    output = env.get("HIA_RENDER_OUTPUT_DIR")
    atomic_json(folder / "launch.json", {**checked, "workspace_id": workspace_id,
                "launcher_session_id": session_id, "hip": str(Path(hip).resolve()) if hip else None,
                "render_output_directory": output, **({"request_id": session_id, "target": target} if target else {})})
    atomic_json(folder / "status.json", {"state": "starting", "process_may_exist": True})
    logs = paths.cache("logs", session_id)
    logs.mkdir(parents=True, exist_ok=True)
    process = None
    try:
        with (logs / "supervisor.log").open("ab") as log:
            process = subprocess.Popen([env["BCS_PYTHON_EXECUTABLE"], "-m", "studio", "supervise",
                                        "--session", session_id],
                                       cwd=paths.root, env=env, stdout=log, stderr=log,
                                       stdin=subprocess.DEVNULL, creationflags=hidden_flags())
    except OSError as exc:
        if process is None:
            atomic_json(folder / "status.json", {"state": "failed", "message": "Supervisor could not start",
                                                "process_may_exist": False})
            raise StudioError("LAUNCH_FAILED", "Supervisor could not start; run setup and check the Python selection") from exc
        # Closing the log can fail after Popen returned. The supervisor now owns
        # status.json; do not overwrite its process facts with a false rejection.
        raise StudioError("LAUNCH_STATE_UNKNOWN", "A process may have started; query this launch again") from exc
    return {"session_id": session_id, "supervisor_pid": process.pid, "directory": str(folder),
            "render_output_directory": output}


def launch_target(paths, target, houdini, codex, *, request_id):
    """Claim the UI's stable request ID once; an ambiguous reply never respawns it."""
    session_id = identifier(request_id)
    value = target.to_dict() if isinstance(target, SceneTarget) else target
    if not isinstance(value, dict) or set(value) - {"kind", "path"}:
        raise StudioError("SCENE_TARGET_INVALID", "Choose one scene target")
    value = dict(value)
    if value.get("kind") == "hip":
        from .targets import hip_path
        value["path"] = str(hip_path(value.get("path"), must_exist=False))
    selected = {"houdini": str(Path(houdini).resolve()), "codex": str(Path(codex).resolve())}
    folder = paths.session(session_id)
    try:
        folder.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        try:
            prior = read_json(folder / "launch.json")
        except (OSError, ValueError):
            return launch_status(paths, session_id)
        if (prior.get("target") != value or
                any(prior.get(key) != item for key, item in selected.items())):
            raise StudioError("LAUNCH_ID_CONFLICT", "This launch ID already belongs to another request", 409)
        return launch_status(paths, session_id)
    atomic_json(folder / "launch.json", {**selected, "request_id": session_id,
                "launcher_session_id": session_id, "target": value})
    atomic_json(folder / "status.json", {"state": "accepted", "process_may_exist": True})
    try:
        target = SceneTarget.from_dict(value)  # Revalidate the file at admission.
        checked = preflight(houdini, codex, paths)
        workspace = SceneCatalog(paths).admit(target)
    except (StudioError, OSError) as exc:
        error = exc.payload()["error"] if isinstance(exc, StudioError) else {
            "code": "LAUNCH_FAILED", "message": "Could not prepare this launch; existing data was preserved"}
        atomic_json(folder / "status.json", {"state": "rejected", "process_may_exist": False,
                                            "message": error["message"], "error": error})
        return launch_status(paths, session_id)
    try:
        spawned = _spawn_session(paths, workspace["workspace_id"], checked, target.path, session_id, target.to_dict())
    except Exception:
        observed = launch_status(paths, session_id)
        if observed["state"] in {"rejected", "closed", "runtime_connected", "target_opened"}:
            return observed
        # Preserve this uncertainty in the request, leaving supervisor status to
        # its owner. The same ID remains query-only even if this write also fails.
        with contextlib.suppress(OSError, ValueError):
            config = read_json(folder / "launch.json")
            atomic_json(folder / "launch.json", {**config, "launch_response_unknown": True})
        return {**observed, "state": "unknown", "process_may_exist": True,
                "message": "A process may have started; query this launch again"}
    value = launch_status(paths, session_id)
    value.setdefault("supervisor_pid", spawned["supervisor_pid"])
    return value


def launch_status(paths, request_id):
    """Read supervisor status plus the Runtime's file-event cache; no HOM or replay."""
    session_id = identifier(request_id)
    folder = paths.session(session_id)
    base = {"request_id": session_id, "session_id": session_id, "directory": str(folder),
            "state": "unknown", "target": None, "runtime_connected": False,
            "target_opened": False, "process_may_exist": True}
    try:
        config = read_json(folder / "launch.json")
        status = read_json(folder / "status.json")
    except (OSError, ValueError):
        return {**base, "message": "Launch state is not confirmed; query this launch again"}
    if config.get("launcher_session_id") != session_id:
        return {**base, "message": "Launch identity does not match its saved status"}
    result = {**base, **status, "target": config.get("target"), "workspace_id": config.get("workspace_id")}
    if result["state"] in {"closed", "rejected"}:
        result["process_may_exist"] = False
        return result
    if result["state"] == "failed":
        possible = bool(status.get("houdini_left_running", status.get("process_may_exist", True)))
        result.update(state="unknown" if possible else "rejected", process_may_exist=possible)
        return result
    if result["state"] in {"accepted", "starting"} and config.get("launch_response_unknown"):
        result.update(state="unknown", process_may_exist=True,
                      message="A process may have started; query this launch again")
    try:
        descriptor = read_json(folder / "runtime.json")
    except (OSError, ValueError):
        return result
    if (descriptor.get("launcher_session_id") != session_id or
            descriptor.get("workspace_id") != config.get("workspace_id") or
            not status.get("houdini_pid") or descriptor.get("houdini_pid") != status["houdini_pid"]):
        return result
    result.update(state="runtime_connected", runtime_connected=True, process_may_exist=True)
    scene, target = descriptor.get("scene", {}), config.get("target") or {}
    if target.get("kind") == "empty":
        opened = scene.get("is_new_file") is True and not scene.get("saved_hip_path")
    else:
        saved = scene.get("saved_hip_path")
        opened = bool(target.get("path") and saved and scene.get("is_new_file") is False and
                      path_key(saved) == path_key(target["path"]) and path_key(scene.get("hip_path", "")) == path_key(saved))
    if scene.get("file_event", {}).get("kind") in {"before_load", "before_clear"}:
        opened = False
    if opened:
        result.update(state="target_opened", target_opened=True)
    else:
        result["message"] = "Studio is connected, but the selected scene has not been confirmed open"
    return result


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
        logs = paths.cache("logs", session_id)
        logs.mkdir(parents=True, exist_ok=True)
        with (logs / "houdini.log").open("ab") as log:
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
                        atomic_json(folder / "status.json", {**status,
                            "state": "runtime_connected" if config.get("target") else "ready"})
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
