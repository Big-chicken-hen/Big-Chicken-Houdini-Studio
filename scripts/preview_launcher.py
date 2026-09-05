"""Explicit launcher-only offscreen review. No Houdini process or AI inference."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT / "src"))

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from studio.common import AppPaths  # noqa: E402
from studio.ui.launcher import StudioLauncher  # noqa: E402


class PreviewWorkspaces:
    """Injectable in-memory fixtures; never written to a user's workspace list."""
    def __init__(self, names=()):
        self.records = [{"workspace_id": "preview_" + str(index), "name": name} for index, name in enumerate(names)]

    def list(self):
        return list(self.records)

    def create(self, name):
        record = {"workspace_id": "preview_" + str(len(self.records)), "name": name}
        self.records.append(record)
        return record


def configure_fonts(app):
    if not QtGui.QFontDatabase.families():
        folder = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf"):
            if (folder / name).is_file():
                QtGui.QFontDatabase.addApplicationFont(str(folder / name))
    app.setFont(QtGui.QFont("Microsoft YaHei UI", 10))


def process_until(predicate, timeout=2500):
    timer = QtCore.QElapsedTimer()
    timer.start()
    while not predicate():
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 20)
        if timer.elapsed() >= timeout:
            raise AssertionError("Qt callback did not arrive")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", default="1")
    parser.add_argument("--case", choices=("all", "high-dpi"), default="all")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_SCALE_FACTOR"] = args.scale
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    output = args.out or APP_ROOT / ".runtime" / "previews" / "launcher-readiness" / (
        time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
    output = output.resolve()
    if APP_ROOT / ".runtime" not in output.parents:
        raise ValueError("Preview output must stay beneath this app's .runtime")
    output.mkdir(parents=True, exist_ok=True)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    configure_fonts(app)
    store = PreviewWorkspaces()
    window = StudioLauncher(paths=AppPaths(APP_ROOT), workspaces=store,
                            installations=[{"label": "Houdini 22.0.368 · 预览环境", "path": "C:/preview/Houdini/bin/houdini.exe"}],
                            codex_path="C:/preview/codex.exe")
    window.show()
    app.processEvents()
    cases = []

    def capture(name):
        target = output / (name + ".png")
        if target.exists():
            raise FileExistsError("Preview already exists: " + str(target))
        # Layout and deferred scroll adjustments settle inside the offscreen app.
        for _ in range(3):
            app.processEvents()
        window.grab().save(str(target))
        cases.append({"file": target.name, "logical_size": [window.width(), window.height()],
                      "device_pixel_ratio": window.devicePixelRatioF()})

    if args.case == "all":
        capture("01-empty-workspace")
    store.records = [{"workspace_id": "preview_0", "name": "雨夜 / 材质与灯光练习"}]
    window.reload_workspaces()
    if args.case == "high-dpi":
        capture("07-high-dpi")
    else:
        capture("02-selected-workspace")
        window.launch_workspace = "preview_0"
        window.sessions["preview_0"] = {"directory": str(output / "fixture-session"), "state": "starting"}
        window.update_selection()
        capture("03-starting")
        window.sessions.clear()
        window.houdini.clear()
        window.codex.clear()
        window.update_selection()
        capture("04-environment-missing")
        long_error = ("[PREVIEW] 所选 Codex 版本与当前协议不匹配。请在启动设置中选择指定版本。\n"
                      "详细原因保持可见并可完整复制；这是离屏错误夹具，不是真实运行故障。\n" +
                      "版本检查明细 / " + "较长的环境路径与诊断文字。" * 32 + "\nEND-OF-ERROR")
        window.failed(long_error)
        capture("05-long-error")
        window.resize(800, 620)
        capture("06-small-window")
        window.resize(1180, 850)
        window.settings_toggle.setChecked(True)
        capture("08-expanded-settings")
    report = {"mode": "native Qt offscreen; explicit in-memory launcher fixtures", "qt": QtCore.qVersion(),
              "python": sys.version.split()[0], "scale": args.scale, "cases": cases,
              "real_houdini_gui": "not run", "codex_inference": "not run"}
    (output / ("report-" + args.case + ".json")).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    window.close()
    print(str(output))


if __name__ == "__main__":
    main()
