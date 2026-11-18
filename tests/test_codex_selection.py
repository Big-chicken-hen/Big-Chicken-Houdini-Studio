"""Installed Codex provenance and explicit choices; no network or native process."""
import os
import unittest
from unittest.mock import patch

import test_onboarding as fixtures
from studio.common import StudioError
from studio.launcher import codex_executable


class CodexSelectionTests(unittest.TestCase):
    setUp = fixtures.OnboardingTests.setUp
    make = fixtures.OnboardingTests.make

    def installed(self):
        (self.paths.root / "release-manifest.json").write_text("{}", encoding="utf-8")
        bundled = self.paths.install("tools", "codex", "bin", "codex.exe" if os.name == "nt" else "codex")
        bundled.parent.mkdir(parents=True)
        bundled.write_bytes(b"fixture native binary")
        return str(bundled)

    def test_bundle_outranks_path_and_old_discovery_cache(self):
        bundled = self.installed()
        value = self.make(["future-codex-0.160.0"])
        value.preferences["codex_verified"] = "old-discovered-codex"
        with patch.dict(os.environ, {"BCS_CODEX_PATH": bundled, "PATH": "future-codex-0.160.0"}), \
                patch.object(value, "candidate_provider", side_effect=AssertionError("installed entry must not discover")):
            result = value.probe()
        self.assertEqual(result["codex"]["path"], bundled)
        self.assertEqual(result["codex"]["source"], "bundled")
        self.assertEqual(len(self.clients), 1)
        self.assertEqual(self.clients[0].command[0], bundled)

    def test_invalid_explicit_override_has_no_fallback_and_empty_choice_restores_bundle(self):
        bundled = self.installed()
        value = self.make(["unexpected-fallback"])
        with patch.dict(os.environ, {"BCS_CODEX_PATH": "incompatible-inherited-external"}):
            result = value.probe(codex_override="incompatible-explicit-external")
            self.assertEqual(result["codex"]["source"], "explicit_external")
            self.assertEqual(result["codex"]["path"], "incompatible-explicit-external")
            self.assertEqual(result["error"]["code"], "CODEX_OVERRIDE_INVALID")
            self.assertEqual(self.clients, [])
            restored = value.probe(codex_override="")
            self.assertEqual(restored["codex"]["path"], bundled)
            self.assertEqual(restored["codex"]["source"], "bundled")
            self.assertEqual(value.probe()["codex"]["path"], bundled)
        self.assertEqual(value.preferences["codex_override"], "")

    def test_inherited_explicit_external_retains_initialize_and_exact_checker(self):
        self.installed()
        value = self.make(["unused-discovery"])
        with patch.dict(os.environ, {"BCS_CODEX_PATH": "compatible-explicit-external"}):
            result = value.probe()
        self.assertEqual(result["codex"]["source"], "explicit_external")
        self.assertEqual(result["codex"]["path"], "compatible-explicit-external")
        self.assertIn(("initialize", {}), self.clients[0].calls)
        self.assertEqual(result["codex"]["version"], "0.153.4")

    def test_missing_or_uninitializable_bundle_never_falls_back(self):
        bundled = self.installed()
        value = self.make(["otherwise-compatible-discovered"])
        value.version_checker = lambda *_args: (_ for _ in ()).throw(StudioError("CODEX_REQUIRED", "bundle missing"))
        with patch.dict(os.environ, {"BCS_CODEX_PATH": ""}), \
                patch.object(value, "candidate_provider", side_effect=AssertionError("must not discover")):
            result = value.probe()
            self.assertEqual(codex_executable(self.paths), bundled)
        self.assertEqual(result["error"]["code"], "CODEX_BUNDLED_INVALID")
        self.assertEqual(result["codex"]["source"], "bundled")
        self.assertEqual(self.clients, [])
        value.version_checker = lambda path, _paths: str(path)
        with patch.dict(os.environ, {"BCS_CODEX_PATH": ""}), \
                patch.object(fixtures.AccountClient, "initialize", side_effect=StudioError("CODEX_UNAVAILABLE", "fixture init failure")):
            self.assertEqual(value.probe()["error"]["code"], "CODEX_BUNDLED_INVALID")
        self.assertEqual(len(self.clients), 1)


if __name__ == "__main__":
    unittest.main()
