"""Small release policy over observed facts; never starts or changes Houdini."""
from __future__ import annotations

from pathlib import Path
import re

from .common import StudioError, identifier


VALIDATED_VERSION = "22.0.368"
GUI_EXECUTABLES = frozenset({name + suffix for name in ("houdini", "houdinifx", "houdinicore", "hescape")
                           for suffix in ("", ".exe")})
PYTHON_ENTRIES = ("3.10", "3.11", "3.13")


def _version(value):
    return tuple(map(int, value.split("."))) if isinstance(value, str) and re.fullmatch(r"\d+\.\d+\.\d+", value) else None


def _edition(facts):
    # Application is a runtime fact, never the executable's basename. A
    # Commercial category alone cannot distinguish the FX and Core products.
    application, license_category = facts.get("application"), facts.get("license_category")
    if license_category in {"Indie", "Education", "Apprentice", "ApprenticeHD"}:
        return license_category
    if license_category == "Commercial":
        for name in (facts.get("application_display_name"), application):
            if name in {"Houdini FX", "houdinifx"}:
                return "FX"
            if name in {"Houdini Core", "houdinicore"}:
                return "Core"
    return None


def classify_houdini(facts):
    """Classify a selected installation or cached runtime facts without a probe.

    Missing edition/host facts remain unknown. For startup only, the observed
    baseline build can enter its existing GUI to obtain those facts; another
    known 22-series version requires an explicit confirmation for that launch.
    """
    version = _version(facts.get("version"))
    edition = _edition(facts)
    integration = facts.get("integration_ready") or {}
    requires_confirmation = bool(version and version[0] == 22 and facts["version"] != VALIDATED_VERSION)

    def result(status, reason, message, *, launch=False):
        return {"status": status, "reason": reason, "message": message, "edition": edition,
                "confirmation_required": bool(launch and requires_confirmation), "can_launch": launch,
                "auto_selectable": bool(launch and version and version[:2] == (22, 0))}

    if (facts.get("ui_available") is False
            or facts.get("application") in {"mplay", "MPlay", "Houdini Engine", "houdiniengine", "hython"}):
        return result("unsupported", "gui_required", "本次发行只接受 Houdini GUI；Engine、MPlay 或无界面入口不支持。")
    if version is None:
        return result("unknown", "version_unconfirmed", "无法确认所选 Houdini 版本，请重新选择可读取版本的安装。")
    if version[0] != 22:
        return result("unsupported", "major_not_supported", "本次发行不支持 Houdini 22 以外的 major 版本。")
    if any(value is False for value in integration.values()):
        return result("unsupported", "integration_missing", "此安装缺少 Studio 所需的 Python、PySide6 或 GUI 启动接入能力。")
    python = _version(facts.get("python_version"))
    qt = _version(facts.get("qt_version"))
    pyside = _version(facts.get("pyside_version"))
    if python and ".".join(map(str, python[:2])) not in PYTHON_ENTRIES:
        return result("unsupported", "python_entry_missing", "此宿主 Python 版本没有随包提供的 Studio GUI 启动接入。")
    if qt and qt[0] != 6 or pyside and pyside[0] != 6:
        return result("unsupported", "qt_integration_missing", "此宿主不具备本次发行所需的 PySide6 / Qt 6 集成。")
    if edition in {"Apprentice", "ApprenticeHD"}:
        return result("unsupported", "edition_not_supported", "本次发行未开放此许可类别的 Studio 试测入口。")
    requires_confirmation = requires_confirmation or edition in {"Core", "Indie", "Education"}
    known_host = (facts.get("ui_available") is True and integration.get("hdefereval") is True
                  and integration.get("panel") is True and python and qt and pyside)
    if edition is None:
        message = "edition / 许可证尚未确认；启动后读取实际宿主事实。"
        if requires_confirmation:
            message = "此 22 系列版本未验证，须确认后试测；" + message
        return result("untested" if requires_confirmation else "unknown", "edition_unconfirmed", message, launch=True)
    if not known_host:
        return result("untested" if requires_confirmation else "unknown", "host_unconfirmed",
                      "宿主 Python / Qt 或 Studio 注册事实尚未确认。", launch=True)
    validated = (facts["version"] == VALIDATED_VERSION and edition == "FX"
                 and facts.get("python_version") == "3.13.10" and facts.get("qt_version") == "6.8.3"
                 and facts.get("pyside_version") == "6.8.3" and facts.get("platform") == "win32"
                 and type(facts.get("windows_build")) is int and facts["windows_build"] >= 22000
                 and isinstance(facts.get("machine"), str) and facts["machine"].lower() in {"amd64", "x86_64"})
    if validated:
        return result("validated", "validated_combination", "已验证：Windows 11 x64 / Houdini FX 22.0.368 / 当前 Python 与 Qt 组合。", launch=True)
    requires_confirmation = True
    return result("untested", "combination_untested", "此 edition / build / 宿主组合未验证，确认后仅作为试测使用。", launch=True)


def inspect_houdini(executable, paths=None):
    """Read a selected executable and known integration paths, without execution."""
    from .release import installed_houdini_version

    path = Path(executable).expanduser().resolve()
    exists = path.is_file()
    facts = {"version": installed_houdini_version(path) if exists else None,
             "ui_available": exists and path.name.lower() in GUI_EXECUTABLES,
             "application": None, "license_category": None}
    if exists and path.parent.name.lower() == "bin":
        installation = path.parent.parent
        entries = [minor for minor in PYTHON_ENTRIES
                   if (installation / "houdini" / ("python" + minor + "libs") / "hdefereval.py").is_file()
                   and any((installation / ("python" + minor.replace(".", "")) / "lib" / folder / "PySide6").is_dir()
                           for folder in ("site-packages-forced", "site-packages"))]
        facts["integration_ready"] = {"hdefereval": bool(entries), "pyside6": bool(entries)}
        if paths is not None:
            facts["integration_ready"]["panel"] = any(
                (paths.root / "houdini" / ("python" + minor + "libs") / "uiready.py").is_file() for minor in entries)
    compatibility = classify_houdini(facts)
    if exists and path.parent.name.lower() != "bin" and compatibility["status"] != "unsupported":
        compatibility.update(status="unknown", reason="integration_root_unconfirmed",
                             message="无法确认此入口对应的 Houdini 安装与基础接入目录；请选择安装内 bin 目录中的 GUI 程序。",
                             can_launch=False, confirmation_required=False, auto_selectable=False)
    return {"path": str(path) if exists else "", "version": facts["version"], "compatibility": compatibility}


def require_houdini_launch(selected, confirmation=None, *, request_id=None):
    compatibility = selected["compatibility"]
    if not compatibility["can_launch"]:
        code = "HOUDINI_UNSUPPORTED" if compatibility["status"] == "unsupported" else "HOUDINI_VERSION_UNKNOWN"
        raise StudioError(code, compatibility["message"], 409)
    if compatibility["confirmation_required"] or confirmation is not None:
        expected_id = request_id if request_id is not None else confirmation.get("request_id") if isinstance(confirmation, dict) else None
        valid = (isinstance(confirmation, dict) and set(confirmation) == {"request_id", "path", "version"}
                 and isinstance(expected_id, str) and confirmation["request_id"] == expected_id
                 and confirmation["path"] == selected["path"] and confirmation["version"] == selected["version"])
        if valid:
            identifier(expected_id)
        else:
            raise StudioError("HOUDINI_UNTESTED_CONFIRMATION_REQUIRED", "请明确确认本次未验证 Houdini 试测启动。", 409,
                              houdini=selected)
    return selected
