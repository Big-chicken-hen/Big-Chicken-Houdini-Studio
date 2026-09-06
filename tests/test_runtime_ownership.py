"""Real OS process/lock faults with fake scene work; never start or kill Houdini."""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from studio import launcher, runtime_server
from studio.common import AppPaths, StudioError, atomic_json, read_json
from studio.ledger import Ledger
from studio.ownership import WorkspaceLock, execution_lock
from studio.runtime import OperationRuntime
from studio.scene import ExecutionResult
from studio.workspace import Workspaces


APP_ROOT = Path(__file__).resolve().parents[1]


def wait_until(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Owned test process did not reach its expected state")


class SceneFixture:
    epoch = "fixture-scene"

    def __init__(self, work=lambda: None):
        self.work = work

    def redact(self, text):
        return text

    def cached(self):
        return {"scene_epoch": self.epoch}

    def refresh_cached(self):
        pass

    def close(self):
        pass

    def error(self, exc, code):
        return {"code": code, "message": "Fixture execution failed"}

    def run(self, kind, arguments, cancelled):
        self.work()
        return ExecutionResult(mutation_outcome="completed")


def operation(runtime):
    return {"operation_id": "owned-operation", "workspace_id": runtime.workspace_id,
            "runtime_id": runtime.runtime_id, "owner_id": "fixture-owner", "scene_epoch": "fixture-scene",
            "kind": "execute", "arguments": {"script": "pass"}}


def executor_fixture():
    """The supervisor starts this Python child in place of a Houdini executable."""
    paths = AppPaths()
    workspace_id, session_id = os.environ["BCS_WORKSPACE_ID"], os.environ["BCS_SESSION_ID"]
    control = Path(os.environ["BCS_OWNERSHIP_CONTROL"])
    def work():
        (control / "entered").touch()
        wait_until(lambda: (control / "release").exists(), timeout=15)
        (control / "effect").write_text("once", encoding="utf-8")
    ownership = execution_lock(paths, workspace_id)
    ledger = Ledger(paths.workspace(workspace_id) / "operations.sqlite")
    runtime = OperationRuntime(ledger, SceneFixture(work), lambda callback: callback(),
                               workspace_id=workspace_id, session_id=session_id, ownership=ownership)
    try:
        runtime.submit(operation(runtime))
        wait_until(lambda: (control / "entered").exists())
        atomic_json(paths.session(session_id) / "runtime.json", {
            "workspace_id": workspace_id, "launcher_session_id": session_id, "houdini_pid": os.getpid()})
        wait_until(lambda: (control / "release").exists(), timeout=15)
    finally:
        runtime.close()
        runtime.worker.join(3)
        if runtime.worker.is_alive():
            raise AssertionError("Fixture worker still owns execution")
        (control / "exited").touch()


def supervisor_fixture(mode):
    """Exercise the actual supervisor finally path, with only Bridge and GUI replaced."""
    paths = AppPaths()
    original_write = launcher.atomic_json
    def write(path, value):
        if mode == "handled" and value.get("state") == "ready":
            raise RuntimeError("Owned test supervisor failure")
        return original_write(path, value)
    # The real Popen launches this file as a Python-only scene executor.
    os.environ["BCS_OWNERSHIP_FIXTURE_CHILD"] = "1"
    with patch("studio.bridge.Bridge"), patch.object(launcher, "atomic_json", side_effect=write):
        return launcher.supervise(paths, os.environ["BCS_SESSION_ID"])


class RuntimeOwnershipTests(unittest.TestCase):
    def setUp(self):
        base = APP_ROOT / ".runtime" / "ownership-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="ownership-", dir=base)
        self.root = Path(self.temp.name)
        (self.root / "pyproject.toml").write_text("[project]\nname='ownership-fixture'\n", encoding="utf-8")
        self.paths = AppPaths(self.root)
        self.workspace = Workspaces(self.paths).create("Execution ownership fixture")["workspace_id"]
        self.control = self.paths.local("control")
        self.control.mkdir(parents=True)
        self.addCleanup(self.temp.cleanup)

    def receipt(self):
        path = self.paths.workspace(self.workspace) / "operations.sqlite"
        # Verification only; contenders below must never invoke Ledger or recovery.
        with contextlib.closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            return json.loads(db.execute("SELECT receipt FROM operations WHERE id='owned-operation'").fetchone()[0])

    def assert_runtime_rejected_before_ledger(self):
        self.paths.session("contender").mkdir(parents=True, exist_ok=True)
        with patch.dict(os.environ, {"BCS_WORKSPACE_ID": self.workspace, "BCS_SESSION_ID": "contender",
                                    "BCS_SESSION_TOKEN": "fixture-only-no-service"}), \
                patch.dict(sys.modules, {"hou": SimpleNamespace(), "hdefereval": SimpleNamespace()}), \
                patch.object(runtime_server, "_session", None), \
                patch.object(runtime_server, "AppPaths", return_value=self.paths), \
                patch.object(runtime_server, "HoudiniScene", side_effect=AssertionError("Contender touched HOM")), \
                patch.object(runtime_server, "Ledger", side_effect=AssertionError("Contender touched ledger")):
            with self.assertRaises(StudioError) as failure:
                runtime_server.start()
        self.assertEqual(failure.exception.code, "WORKSPACE_IN_USE")
        startup_error = read_json(self.paths.session("contender") / "runtime-error.json")
        self.assertEqual(startup_error["error"]["code"], "WORKSPACE_IN_USE")

    def test_supervisor_normal_handled_and_forced_exit_preserve_child_ownership(self):
        # Windows venv python.exe is a redirector: its Popen PID differs from
        # os.getpid() in the interpreter it launches. Fixtures need the real
        # executable both for production registration and the owned-parent kill.
        fixture_python = launcher.console_python(getattr(sys, "_base_executable", sys.executable))
        for mode in ("normal", "handled", "terminated"):
            with self.subTest(mode=mode):
                # Each mode uses another workspace and control directory under this test root.
                self.workspace = Workspaces(self.paths).create(mode)["workspace_id"]
                session_id = "session-" + mode
                folder = self.paths.session(session_id)
                folder.mkdir(parents=True)
                self.control = self.paths.local("control-" + mode)
                self.control.mkdir()
                atomic_json(folder / "launch.json", {"launcher_session_id": session_id,
                    "workspace_id": self.workspace, "houdini": fixture_python, "codex": "unused-fixture",
                    "hip": str(Path(__file__).resolve())})
                env = {**os.environ, "HIA_PROJECT_ROOT": str(self.root), "PYTHONPATH": str(APP_ROOT / "src"),
                       "PYTHONDONTWRITEBYTECODE": "1", "BCS_SESSION_ID": session_id,
                       "BCS_WORKSPACE_ID": self.workspace, "BCS_SESSION_TOKEN": "fixture-only-no-service",
                       "BCS_OWNERSHIP_CONTROL": str(self.control)}
                env.pop("BCS_OWNERSHIP_FIXTURE_CHILD", None)
                parent = subprocess.Popen([fixture_python, "-B", str(Path(__file__).resolve()), "--supervisor", mode],
                                          cwd=APP_ROOT, env=env, stdin=subprocess.DEVNULL,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                          creationflags=launcher.hidden_flags())
                child_handle = None
                try:
                    def ready():
                        if parent.poll() is not None:
                            raise AssertionError(parent.stderr.read().decode("utf-8", "replace"))
                        status = read_json(folder / "status.json") if (folder / "status.json").exists() else {}
                        return status.get("state") == ("failed" if mode == "handled" else "ready")
                    wait_until(ready)
                    child_pid = read_json(folder / "runtime.json")["houdini_pid"]
                    if os.name == "nt":
                        import ctypes
                        from ctypes import wintypes
                        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                        kernel.OpenProcess.restype = wintypes.HANDLE
                        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                        child_handle = kernel.OpenProcess(0x00100000, False, child_pid)  # SYNCHRONIZE only
                        self.assertTrue(child_handle)
                    self.assertEqual(self.receipt()["state"], "running")
                    self.assert_runtime_rejected_before_ledger()
                    if mode == "terminated":
                        # This handle is the exact temporary supervisor created just above.
                        parent.kill()
                        parent.wait(3)
                        # The parent reservation is gone, while child-owned execution remains.
                        wait_until(lambda: self.reservation_available())
                        self.assertFalse((self.control / "exited").exists())
                        self.assert_runtime_rejected_before_ledger()
                        # A fresh supervisor reports the orphaned executor without
                        # starting Bridge or another fake GUI.
                        contender = self.paths.session("fresh-supervisor")
                        contender.mkdir()
                        atomic_json(contender / "launch.json", {"launcher_session_id": "fresh-supervisor",
                            "workspace_id": self.workspace, "houdini": fixture_python, "codex": "unused"})
                        with patch.dict(os.environ, {"BCS_SESSION_ID": "fresh-supervisor",
                            "BCS_WORKSPACE_ID": self.workspace, "BCS_SESSION_TOKEN": "fixture-only"}), \
                                patch("studio.bridge.Bridge") as bridge, \
                                patch.object(launcher.subprocess, "Popen") as spawn:
                            self.assertEqual(launcher.supervise(self.paths, "fresh-supervisor"), 1)
                            bridge.assert_not_called()
                            spawn.assert_not_called()
                        self.assertIn("runtime still owns", read_json(contender / "status.json")["message"])
                    else:
                        with self.assertRaises(StudioError):
                            WorkspaceLock(self.paths.workspace(self.workspace) / "session.lock")
                    self.assertEqual(self.receipt()["state"], "running")
                finally:
                    (self.control / "release").touch()
                    try:
                        if (self.control / "entered").exists():
                            wait_until(lambda: (self.control / "exited").exists())
                    finally:
                        if parent.poll() is None:
                            try:
                                parent.wait(5)
                            except subprocess.TimeoutExpired:
                                parent.kill()  # Only this test's Popen handle, never a PID search.
                                parent.wait(3)
                        if child_handle:
                            try:
                                self.assertEqual(kernel.WaitForSingleObject(child_handle, 5000), 0)
                            finally:
                                kernel.CloseHandle(child_handle)
                        parent.stderr.close()
                self.assertEqual((self.control / "effect").read_text(encoding="utf-8"), "once")
                self.assertEqual(self.receipt()["state"], "finished")
                execution_lock(self.paths, self.workspace).close()
                if mode != "terminated":
                    self.assertEqual(parent.returncode, 1 if mode == "handled" else 0)

    def reservation_available(self):
        try:
            WorkspaceLock(self.paths.workspace(self.workspace) / "session.lock").close()
            return True
        except StudioError:
            return False

    def test_close_timeout_keeps_ownership_through_final_receipt(self):
        started, release = threading.Event(), threading.Event()
        def work():
            started.set()
            if not release.wait(8):
                raise AssertionError("Fixture did not release scene work")
        ownership = execution_lock(self.paths, self.workspace)
        ledger = Ledger(self.paths.workspace(self.workspace) / "operations.sqlite")
        runtime = OperationRuntime(ledger, SceneFixture(work), lambda callback: callback(),
                                   workspace_id=self.workspace, session_id="fixture", ownership=ownership)
        try:
            runtime.submit(operation(runtime))
            self.assertTrue(started.wait(2))
            runtime.close()  # Its bounded join expires with scene work still running.
            self.assertTrue(runtime.worker.is_alive())
            self.assert_runtime_rejected_before_ledger()
            self.assertEqual(self.receipt()["state"], "running")
        finally:
            release.set()
            runtime.worker.join(3)
            self.assertFalse(runtime.worker.is_alive())
        self.assertEqual(self.receipt()["state"], "finished")
        execution_lock(self.paths, self.workspace).close()

    def test_startup_failures_release_ownership_and_close_open_ledger(self):
        opened = []
        def open_ledger(*args, **kwargs):
            value = Ledger(*args, **kwargs)
            opened.append(value)
            return value
        for failure_at in ("ledger", "server"):
            with self.subTest(failure_at=failure_at), \
                    patch.dict(os.environ, {"BCS_WORKSPACE_ID": self.workspace, "BCS_SESSION_ID": "startup",
                                            "BCS_SESSION_TOKEN": "fixture-only-no-service"}), \
                    patch.dict(sys.modules, {"hou": SimpleNamespace(), "hdefereval": SimpleNamespace(
                        executeInMainThreadWithResult=lambda callback: callback())}), \
                    patch.object(runtime_server, "_session", None), \
                    patch.object(runtime_server, "AppPaths", return_value=self.paths), \
                    patch.object(runtime_server, "HoudiniScene", return_value=SceneFixture()), \
                    patch.object(runtime_server, "serve", side_effect=RuntimeError("server startup failed")):
                ledger = Mock(side_effect=RuntimeError("ledger startup failed")) if failure_at == "ledger" else open_ledger
                with patch.object(runtime_server, "Ledger", ledger):
                    with self.assertRaisesRegex(RuntimeError, "startup failed"):
                        runtime_server.start()
                execution_lock(self.paths, self.workspace).close()
                if failure_at == "server":
                    with self.assertRaises(sqlite3.ProgrammingError):
                        opened[-1].db.execute("SELECT 1")

    def test_startup_conflict_is_reported_instead_of_remaining_starting(self):
        session_id = "lost-race"
        folder = self.paths.session(session_id)
        folder.mkdir(parents=True)
        atomic_json(folder / "launch.json", {"launcher_session_id": session_id,
            "workspace_id": self.workspace, "houdini": "unused-fixture", "codex": "unused-fixture"})
        atomic_json(folder / "runtime-error.json", {"launcher_session_id": session_id,
            "workspace_id": self.workspace, "error": {"code": "WORKSPACE_IN_USE", "message": "Runtime owns workspace"}})
        process = Mock(pid=123, returncode=None)
        process.poll.return_value = None
        with patch.dict(os.environ, {"BCS_SESSION_ID": session_id, "BCS_WORKSPACE_ID": self.workspace,
                                     "BCS_SESSION_TOKEN": "fixture-only"}), \
                patch("studio.bridge.Bridge"), patch.object(launcher.subprocess, "Popen", return_value=process), \
                patch.object(launcher.time, "sleep", side_effect=AssertionError("Must report the startup conflict")):
            self.assertEqual(launcher.supervise(self.paths, session_id), 1)
        status = read_json(folder / "status.json")
        self.assertEqual((status["state"], status["message"]), ("failed", "Runtime owns workspace"))
        self.assertTrue(status["houdini_left_running"])
        process.wait.assert_called_once()
        process.kill.assert_not_called()
        process.terminate.assert_not_called()


if __name__ == "__main__":
    if "--supervisor" in sys.argv:
        raise SystemExit(supervisor_fixture(sys.argv[-1]))
    if os.environ.get("BCS_OWNERSHIP_FIXTURE_CHILD") == "1":
        executor_fixture()
    else:
        unittest.main()
