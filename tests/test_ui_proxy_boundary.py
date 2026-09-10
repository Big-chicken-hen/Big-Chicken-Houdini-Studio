"""Qt delivery uses the same direct loopback boundary with only fixture data."""
import os
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6 import QtWidgets  # noqa: E402
from scripts.preview_ui import process_until  # noqa: E402
from studio.ui.shared import Api  # noqa: E402
import test_http_proxy_boundary as fixtures  # noqa: E402


class PanelProxyTests(fixtures.ProxyFixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_panel_client_ignores_case_varied_proxy_environment_without_exceptions(self):
        for name, environment in self.environments():
            with self.subTest(name=name), patch.dict(os.environ, environment, clear=True):
                api, done, failed = Api(self.url, self.token), [], []
                try:
                    api.call('POST', '/fixture', {'marker': name}, done=done.append, failed=failed.append)
                    process_until(lambda: bool(done or failed))
                    self.assertEqual(failed, [])
                    self.assertEqual(done, [{'received': name}])
                finally:
                    api.close()
        self.assertEqual(self.proxy_calls, [])
        self.assertEqual(self.direct_calls, [('POST', '/fixture')] * 3)
