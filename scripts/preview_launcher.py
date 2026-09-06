"""Bounded offscreen Launcher fixtures. No programs, accounts or HIPs are opened."""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT / "src"))

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from studio.common import AppPaths, StudioError  # noqa: E402
from studio.ui.launcher import StudioLauncher  # noqa: E402
from studio.ui.shared import ApiFailure  # noqa: E402


@dataclass(frozen=True)
class PreviewTarget:
    kind: str
    path: str | None = None

    @classmethod
    def empty(cls):
        return cls("empty")

    @classmethod
    def hip(cls, path):
        # Intentionally in-memory target validation, not a real HIP existence check.
        if Path(path).suffix.lower() not in {".hip", ".hiplc", ".hipnc"} or "missing" in str(path):
            raise StudioError("HIP_INVALID", "找不到此场景文件，请重新定位")
        return cls("hip", str(path))

    def to_dict(self):
        return {"kind": self.kind, "path": self.path}


class PreviewOnboarding:
    def __init__(self, services, paths):
        self.services = services
        self.paths = paths
        self.closed = False

    def probe(self, **overrides):
        if self.closed:
            raise AssertionError("A closed onboarding instance was reused")
        self.services.probes.append(overrides)
        if self.services.probe_gate:
            self.services.probe_gate.wait(2)
        return self.services.snapshot()

    def account_read(self):
        return self.services.snapshot()

    def login_start(self):
        self.services.state = "waiting"
        return {**self.services.snapshot(), "auth_url": "https://example.invalid/login?state=fixture"}

    def reopen_login(self):
        return "https://example.invalid/login?state=fixture"

    def cancel_login(self):
        self.services.state = "signed_out"
        return self.services.snapshot()

    def logout(self):
        self.services.state = "signed_out"
        return self.services.snapshot()

    def prepare_launch(self):
        if self.services.state != "ready":
            raise StudioError("CHATGPT_REQUIRED", "请先确认 ChatGPT 登录")
        self.close()
        return {"codex_path": "C:/fixture/codex.exe", "houdini_path": "C:/fixture/houdini.exe",
                "codex_home": str(self.paths.codex_home)}

    def remember_houdini(self, path):
        self.services.remembered.append(path)

    def close(self):
        if not self.closed:
            self.services.lifecycle.append(("closed", self.paths))
        self.closed = True


class PreviewServices:
    def __init__(self, state="ready", records=None):
        self.state = state
        self.records = copy.deepcopy(records if records is not None else [
            {"path": "D:/Projects/Furniture/Bookcase/bookcase_v06.hip", "name": "bookcase_v06.hip",
             "directory": "D:/Projects/Furniture/Bookcase", "last_used_at": 1788670800,
             "workspace_id": "fixture-bookcase", "missing": False},
            {"path": "D:/Projects/空间与比例/入口场景.hiplc", "name": "入口场景.hiplc",
             "directory": "D:/Projects/空间与比例", "last_used_at": 1788574800,
             "workspace_id": "fixture-layout", "missing": False},
        ])
        self.probes, self.backends, self.launches, self.queries, self.opened_urls, self.remembered = [], [], [], [], [], []
        self.admissions = {}
        self.launch_state = "starting"
        self.lose_launch = False
        self.probe_gate = None
        self.launch_gate = None
        self.paths = AppPaths(APP_ROOT)
        self.lifecycle = []

    def factory(self):
        self.lifecycle.append(("created", self.paths))
        backend = PreviewOnboarding(self, self.paths)
        self.backends.append(backend)
        return backend

    def snapshot(self):
        account_status = {"ready": "signed_in", "signed_out": "signed_out", "waiting": "waiting",
                          "account_unknown": "unknown", "other": "other"}.get(self.state, "signed_out")
        return {"revision": len(self.probes), "codex": {
            "state": "missing" if self.state == "missing_codex" else "ready",
            "path": "C:/fixture/codex.exe", "version": "0.153.4", "message": ""},
            "houdini": {"state": "missing" if self.state == "missing_houdini" else "found",
                         "path": "C:/fixture/houdini.exe", "version": "22.0.368", "message": "",
                         "installations": [{"path": "C:/fixture/houdini.exe", "label": "Houdini 22.0.368"}]},
            "account": {"status": account_status, "type": "chatgpt" if account_status == "signed_in" else None,
                        "login_pending": account_status == "waiting", "action_unknown": False,
                        "email": "artist@example.invalid" if account_status == "signed_in" else None},
            "error": None}

    def recent(self, limit=20):
        return copy.deepcopy(self.records[:limit])

    def remove_recent(self, path):
        self.records = [r for r in self.records if r["path"] != path]

    def relocate_recent(self, old_path, new_path):
        target = PreviewTarget.hip(new_path)
        for record in self.records:
            if record["path"] == old_path:
                record.update(path=target.path, name=Path(target.path).name,
                              directory=str(Path(target.path).parent), missing=False)

    def launch(self, paths, target, houdini, codex, *, request_id):
        self.launches.append((target.to_dict(), request_id, houdini, codex))
        if self.launch_gate:
            self.launch_gate.wait(2)
        self.admissions[request_id] = {"request_id": request_id, "session_id": request_id,
            "state": self.launch_state, "target": target.to_dict(), "workspace_id": "fixture-context",
            "directory": str(paths.local("fixture-session")), "runtime_connected": self.launch_state == "target_opened",
            "target_opened": self.launch_state == "target_opened", "process_may_exist": True}
        if self.lose_launch:
            raise StudioError("CONNECTION_LOST", "启动响应暂不可确认", 503)
        return dict(self.admissions[request_id])

    def query(self, paths, request_id):
        self.queries.append(request_id)
        return dict(self.admissions.get(request_id, {"request_id": request_id, "state": "unknown",
                                                    "process_may_exist": True}))

    def open_browser(self, url):
        self.opened_urls.append(url.toString())
        return True


def configure_fonts(app):
    if not QtGui.QFontDatabase.families():
        folder = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf"):
            if (folder / name).is_file():
                QtGui.QFontDatabase.addApplicationFont(str(folder / name))
    # This function is used only by the standalone offscreen fixtures.
    app.setFont(QtGui.QFont("Microsoft YaHei UI", 10))


def process_until(predicate, timeout=2500):
    timer = QtCore.QElapsedTimer()
    timer.start()
    while not predicate():
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 20)
        if timer.elapsed() >= timeout:
            raise AssertionError("Qt callback did not arrive")


def make_fixture_window(paths=None, state="ready", records=None, services=None):
    services = services or PreviewServices(state, records)
    services.paths = paths or AppPaths(APP_ROOT)
    window = StudioLauncher(paths=services.paths, onboarding_factory=services.factory,
                            catalog=services, target_factory=PreviewTarget, launch_function=services.launch,
                            status_function=services.query, browser_open=services.open_browser)
    window.show()
    process_until(lambda: not window._pending)
    return window, services


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", default="1")
    parser.add_argument("--case", choices=("all", "high-dpi", "first-use"), default="all")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_SCALE_FACTOR"] = args.scale
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    output = args.out or APP_ROOT / ".runtime" / "previews" / "launcher-productization" / (
        time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
    output = output.resolve()
    if APP_ROOT / ".runtime" not in output.parents:
        raise ValueError("Preview output must stay beneath this app's .runtime")
    output.mkdir(parents=True, exist_ok=True)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    configure_fonts(app)
    cases = []

    def capture(window, name):
        for _ in range(3):
            app.processEvents()
        target = output / (name + ".png")
        if target.exists():
            raise FileExistsError("Preview already exists: " + str(target))
        if not window.grab().save(str(target)):
            raise RuntimeError("Preview could not be saved")
        corner = window.launch_button.mapTo(window, QtCore.QPoint(window.launch_button.width(), window.launch_button.height()))
        if corner.x() > window.width() or corner.y() > window.height():
            raise AssertionError("Main action extends outside Launcher")
        readiness_rows = []
        for row in (window.account_row, window.codex_row, window.houdini_row):
            # Scrollable content can be offscreen, but its own rows must never be
            # clipped by the readiness frame or shrink below wrapped text height.
            if not row.parentWidget().rect().contains(row.geometry()):
                raise AssertionError("Readiness row extends outside its frame")
            if row.text.height() < row.text.heightForWidth(row.text.width()):
                raise AssertionError("Readiness status text is clipped")
            readiness_rows.append({"title": row.title.text(), "rect": list(row.geometry().getRect()),
                                   "text_rect": list(row.text.geometry().getRect())})
        cases.append({"file": target.name, "logical_size": [window.width(), window.height()],
                      "device_pixel_ratio": window.devicePixelRatioF(), "readiness_rows": readiness_rows})

    first_use = args.case == "first-use"
    window, services = make_fixture_window(state="signed_out" if first_use else "ready",
                                          records=[] if first_use else None)
    capture(window, "00-first-use" if first_use else "01-ready")
    if args.case == "all":
        for state, name in (("signed_out", "02-sign-in"), ("missing_codex", "03-codex-missing"),
                            ("missing_houdini", "04-houdini-missing"), ("waiting", "05-browser-waiting")):
            services.state = state
            window.apply_snapshot(services.snapshot())
            window.render()
            capture(window, name)
        services.state = "ready"
        window.apply_snapshot(services.snapshot())
        window.render()
        window.start_session()
        process_until(lambda: window._launch_phase is None)
        capture(window, "06-starting")
        services.admissions[window._request_id]["state"] = "unknown"
        window.query_launch()
        process_until(lambda: "status" not in window._pending)
        window.show_failure(ApiFailure("启动结果尚未确认，请查询原请求。", code="LAUNCH_UNKNOWN",
                            details={"message": "离屏夹具 · " + "较长的程序路径和诊断说明。" * 16}))
        window.error_details.toggle.setChecked(True)
        window.render()
        capture(window, "07-unknown-details")
    window.resize(560, 600)
    window.render()
    capture(window, "08-compact")
    report = {"mode": "native Qt offscreen; in-memory scene/readiness/launch fixtures", "qt": QtCore.qVersion(),
              "scale": args.scale, "cases": cases, "real_houdini_gui": "not run", "official_login": "not run",
              "cross_monitor_dpi_transition": "not run"}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    window.close()
    print(str(output))


if __name__ == "__main__":
    main()
