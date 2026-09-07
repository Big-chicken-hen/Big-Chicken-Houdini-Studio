"""Finite presentation of existing Launcher facts; no service calls or mutations."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LauncherPage:
    name: str
    mode: str = ""


def project_page(snapshot, *, request_id=None, launch_record=None, launch_phase=None, checking=False):
    if request_id is not None:
        record = launch_record or {}
        state = record.get("state")
        if launch_phase:
            return LauncherPage("launching", launch_phase)
        if state == "target_opened" and record.get("runtime_connected") and record.get("target_opened"):
            return LauncherPage("launching", "opened")
        if state in {"closed", "rejected"} and not record.get("process_may_exist"):
            return LauncherPage("launching", "failed")
        if state == "runtime_connected":
            return LauncherPage("launching", "scene")
        if state in {"accepted", "starting"}:
            return LauncherPage("launching", "connecting")
        return LauncherPage("launching", "unknown")
    codex, houdini, account = (snapshot.get(key) or {} for key in ("codex", "houdini", "account"))
    state = codex.get("state")
    if checking or state in {None, "checking"}:
        return LauncherPage("checking")
    if state != "ready":
        if state == "missing":
            return LauncherPage("setup", "codex_missing")
        attempts = codex.get("attempts") or []
        codes = [str(item.get("code") or "") for item in attempts if isinstance(item, dict)]
        if state == "incompatible" and codes and all("VERSION" in code for code in codes):
            return LauncherPage("setup", "codex_incompatible")
        initialization_errors = {"CODEX_UNAVAILABLE", "CODEX_START_FAILED", "CODEX_NOT_RUNNING",
                                 "CODEX_REQUEST_TIMEOUT", "CODEX_STDIN_FAILED"}
        if state == "error" or any(code in initialization_errors for code in codes):
            return LauncherPage("setup", "codex_error")
        return LauncherPage("setup", "codex_unconfirmed")
    if houdini.get("state") != "found":
        return LauncherPage("setup", "houdini")
    if account.get("action_unknown"):
        return LauncherPage("authentication", "attention")
    status = account.get("status", "unknown")
    if status == "signed_in":
        return LauncherPage("home")
    if status == "waiting":
        return LauncherPage("authentication", "waiting")
    if status in {"signed_out", "other"}:
        return LauncherPage("authentication", "signed_out")
    return LauncherPage("authentication", "attention")
