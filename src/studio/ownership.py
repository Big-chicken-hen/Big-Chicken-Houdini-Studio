"""Process-owned workspace locks; no PID guessing, lease or automatic recovery."""
from __future__ import annotations

import os
from pathlib import Path

from .common import StudioError


class WorkspaceLock:
    """Hold an OS lock until close or process death; never delete the lock file."""
    def __init__(self, path, message="This workspace already has a running Studio session"):
        self.file = Path(path).open("a+b")
        try:
            self.file.seek(0, 2)
            if self.file.tell() == 0:
                self.file.write(b"0")
                self.file.flush()
            self.file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise StudioError("WORKSPACE_IN_USE", message, 409) from exc

    def close(self):
        self.file.close()


def execution_lock(paths, workspace_id):
    return WorkspaceLock(paths.workspace(workspace_id) / "execution.lock",
                         "A Houdini runtime still owns this workspace; close that session before reopening it")
