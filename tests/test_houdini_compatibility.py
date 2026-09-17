"""Release-policy and selection faults only; no actual host compatibility claim."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_onboarding as fixtures
from studio.common import AppPaths, StudioError, new_id
from studio.houdini_compatibility import classify_houdini, inspect_houdini
from studio.launcher import preflight
from studio.onboarding import Onboarding


class HoudiniCompatibilityTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[1] / ".runtime" / "compatibility-tests"
        base.mkdir(parents=True, exist_ok=True)
        folder = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / "pyproject.toml").write_text("# fixture", encoding="utf-8")
        self.paths = AppPaths(self.root)
        self.versions = {}
        self.host = {"version": "22.0.368", "application": "houdini", "application_display_name": "Houdini FX",
                     "license_category": "Commercial", "ui_available": True, "python_version": "3.13.10",
                     "qt_version": "6.8.3", "pyside_version": "6.8.3", "platform": "win32", "windows_build": 22631,
                     "machine": "AMD64", "integration_ready": {"hdefereval": True, "panel": True}}
        for minor in ("3.10", "3.11", "3.13"):
            hook = self.root / "houdini" / ("python" + minor + "libs") / "uiready.py"
            hook.parent.mkdir(parents=True)
            hook.write_text("# fixture", encoding="utf-8")
        self.reader = patch("studio.release.installed_houdini_version", side_effect=lambda path: self.versions.get(str(path)))
        self.reader.start()
        self.addCleanup(self.reader.stop)

    def installation(self, version, name="houdini.exe"):
        root = self.root / ("Houdini " + version)
        executable = root / "bin" / name
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"not an executable; version resource reader is controlled")
        deferred = root / "houdini" / "python3.13libs" / "hdefereval.py"
        deferred.parent.mkdir(parents=True, exist_ok=True)
        deferred.write_text("# fixture", encoding="utf-8")
        (root / "python313" / "lib" / "site-packages-forced" / "PySide6").mkdir(parents=True, exist_ok=True)
        self.versions[str(executable)] = version
        return str(executable)

    def onboarding(self, paths):
        value = Onboarding(self.paths, client_factory=fixtures.AccountClient, version_checker=lambda path, _paths: str(path),
                           candidate_provider=lambda *_: ["controlled-codex"],
                           houdini_provider=lambda: [{"path": path, "label": "fixture"} for path in paths])
        self.addCleanup(value.close)
        return value

    def test_four_classes_use_actual_facts_and_never_infer_fx_from_commercial_or_basename(self):
        self.assertEqual(classify_houdini(self.host)["status"], "validated")
        for changes in ({"version": "22.0.400"}, {"version": "22.1.1"},
                        {"application_display_name": "Houdini Core"}, {"license_category": "Indie"},
                        {"license_category": "Education"}, {"qt_version": "6.8.4"}):
            with self.subTest(changes=changes):
                value = classify_houdini({**self.host, **changes})
                self.assertEqual(value["status"], "untested")
                self.assertTrue(value["confirmation_required"])
        self.assertFalse(classify_houdini({**self.host, "version": "22.1.1"})["auto_selectable"])
        for changes in ({"version": "21.0.123"}, {"ui_available": False}, {"application": "mplay"},
                        {"python_version": "3.12.1"}, {"integration_ready": {"panel": False}}):
            self.assertEqual(classify_houdini({**self.host, **changes})["status"], "unsupported")
        unknown = classify_houdini({**self.host, "application_display_name": "", "executable": "houdinifx.exe"})
        self.assertEqual(unknown["status"], "unknown")
        self.assertIsNone(unknown["edition"])
        self.assertEqual(classify_houdini({**self.host, "version": None})["status"], "unknown")

    def test_selected_baseline_unknown_edition_launches_and_adjacent_build_needs_exact_confirmation(self):
        baseline, other = self.installation("22.0.368"), self.installation("22.0.400")
        with patch("studio.launcher.check_codex", return_value="controlled-codex"):
            result = preflight(baseline, "controlled-codex", self.paths)
            self.assertEqual(result["houdini_selected"]["compatibility"]["status"], "unknown")
            self.assertFalse(result["houdini_confirmation"])
            request_id = new_id()
            confirmation = {"request_id": request_id, "path": other, "version": "22.0.400"}
            for supplied in (None, True, {**confirmation, "request_id": new_id()},
                             {**confirmation, "path": baseline}, {**confirmation, "version": "22.0.399"}):
                with self.subTest(supplied=supplied), self.assertRaises(StudioError):
                    preflight(other, "controlled-codex", self.paths, houdini_confirmation=supplied, request_id=request_id)
            accepted = preflight(other, "controlled-codex", self.paths, houdini_confirmation=confirmation, request_id=request_id)
            self.assertTrue(accepted["houdini_confirmation"])
            self.assertNotEqual(accepted["houdini_selected"]["compatibility"]["status"], "validated")
            self.versions[other] = "22.0.401"
            with self.assertRaises(StudioError):
                preflight(other, "controlled-codex", self.paths, houdini_confirmation=confirmation, request_id=request_id)

    def test_selection_preserves_user_choice_and_never_auto_picks_future_minor(self):
        baseline, other, future = (self.installation(version) for version in ("22.0.368", "22.0.400", "22.1.1"))
        value = self.onboarding([future, other, baseline])
        value._houdini(None)
        self.assertEqual(value.houdini["path"], baseline)
        value.preferences["last_houdini"] = other
        value._houdini(None)
        self.assertEqual(value.houdini["path"], other)
        value._houdini(future)
        self.assertEqual(value.houdini["path"], future)
        self.assertTrue(value.houdini["compatibility"]["confirmation_required"])
        fresh = self.onboarding([future])
        fresh._houdini(None)
        self.assertEqual(fresh.houdini["state"], "missing")

    def test_prepare_rechecks_confirmation_and_does_not_persist_risk_permission(self):
        executable = self.installation("22.0.400")
        value = self.onboarding([executable])
        value.probe()
        with self.assertRaises(StudioError):
            value.prepare_launch()
        confirmation = {"request_id": new_id(), "path": executable, "version": "22.0.400"}
        before = copy.deepcopy(value.preferences)
        result = value.prepare_launch(confirmation)
        self.assertEqual(result["houdini_confirmation"], confirmation)
        self.assertEqual(value.preferences, before)
        self.assertNotIn("houdini_confirmation", value.preferences)

    def test_missing_integration_and_unknown_version_fail_before_codex_probe(self):
        executable = self.installation("22.0.400")
        with patch("studio.launcher.check_codex", side_effect=AssertionError("must reject before Codex execution")):
            self.versions[executable] = None
            with self.assertRaises(StudioError) as error:
                preflight(executable, "unused", self.paths)
            self.assertEqual(error.exception.code, "HOUDINI_VERSION_UNKNOWN")
            self.versions[executable] = "22.0.400"
            with patch("studio.houdini_compatibility.Path.is_dir", return_value=False):
                value = inspect_houdini(executable, self.paths)
            self.assertEqual(value["compatibility"]["status"], "unsupported")

    def test_non_bin_gui_with_known_version_cannot_bypass_installation_root_checks(self):
        executable = self.root / "copied-gui" / "houdini.exe"
        executable.parent.mkdir()
        executable.write_bytes(b"fixture copied GUI; controlled PE version")
        self.versions[str(executable)] = "22.0.368"
        value = inspect_houdini(executable, self.paths)
        self.assertEqual(value["version"], "22.0.368")
        self.assertEqual(value["compatibility"]["status"], "unknown")
        self.assertEqual(value["compatibility"]["reason"], "integration_root_unconfirmed")
        self.assertFalse(value["compatibility"]["can_launch"])
        with patch("studio.launcher.check_codex", side_effect=AssertionError("no Codex probe for unidentified install root")):
            with self.assertRaises(StudioError):
                preflight(executable, "unused", self.paths)


if __name__ == "__main__":
    unittest.main()
