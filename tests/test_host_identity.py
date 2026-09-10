"""Registration facts are cached, optional and separate from scene observations."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from studio.common import AppPaths
from studio.host_identity import collect_host_identity
from studio.runtime_server import runtime_router


class HostIdentityTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / '.runtime/host-identity-tests'
        root.mkdir(parents=True, exist_ok=True)
        folder = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(folder.cleanup)
        (Path(folder.name)/'pyproject.toml').write_text('[project]', encoding='utf-8')
        self.paths = AppPaths(Path(folder.name), data_root=Path(folder.name)/'state', cache_root=Path(folder.name)/'cache')
        source = self.paths.root/'houdini/python_panels/big_chicken_studio.pypanel'
        self.hou = SimpleNamespace(applicationVersionString=Mock(return_value='22.0.368'),
            applicationName=Mock(return_value='houdini'), isUIAvailable=Mock(return_value=True),
            licenseCategory=Mock(return_value=SimpleNamespace(name=lambda: 'Commercial')),
            pypanel=SimpleNamespace(interfaceByName=Mock(return_value=SimpleNamespace(filePath=lambda: str(source)))))
        self.modules = {'PySide6': SimpleNamespace(__version__='6.8.3'),
            'PySide6.QtCore': SimpleNamespace(qVersion=lambda: '6.8.3'),
            'PySide6.QtGui': SimpleNamespace(QGuiApplication=SimpleNamespace(applicationDisplayName=lambda: 'Houdini FX'))}

    def test_once_collected_actual_fields_are_not_a_filename_or_license_guess(self):
        value = collect_host_identity(self.hou, self.paths, lambda: None, modules=self.modules)
        self.assertEqual((value['application'], value['application_display_name'], value['license_category']),
                         ('houdini', 'Houdini FX', 'Commercial'))
        self.assertEqual(value['version'], '22.0.368')
        self.assertEqual(value['integration_ready'], {'hdefereval': True, 'panel': True, 'pyside6': True})
        for name in ('applicationVersionString', 'applicationName', 'licenseCategory', 'isUIAvailable'):
            getattr(self.hou, name).assert_called_once()
        self.hou.pypanel.interfaceByName.assert_called_once_with('big_chicken_studio')

    def test_missing_facts_are_null_and_wrong_registered_source_is_explicit(self):
        self.hou.licenseCategory.side_effect = RuntimeError('unavailable')
        self.hou.pypanel.interfaceByName.return_value.filePath = lambda: str(self.paths.root/'old.pypanel')
        value = collect_host_identity(self.hou, self.paths, lambda: None, modules={})
        self.assertIsNone(value['license_category'])
        self.assertIsNone(value['qt_version'])
        self.assertIsNone(value['application_display_name'])
        self.assertFalse(value['integration_ready']['panel'])
        self.assertEqual(value['compatibility']['status'], 'unsupported')
        self.hou.pypanel.interfaceByName.side_effect = RuntimeError('registration not readable')
        value = collect_host_identity(self.hou, self.paths, lambda: None, modules=self.modules)
        self.assertIsNone(value['integration_ready']['panel'])
        self.assertEqual(value['compatibility']['status'], 'unknown')

    def test_health_delivers_only_copied_registration_facts_without_hom(self):
        host = {'version': '22.0.368', 'integration_ready': {'panel': True}}
        runtime = SimpleNamespace(health=lambda: {'scene': {'scene_epoch': 'original'}, 'main_thread_busy': False})
        router = runtime_router(runtime, host)
        host['version'] = 'changed-after-registration'
        with patch('studio.host_identity.collect_host_identity', side_effect=AssertionError('No repeated host probe')):
            first = router('GET', '/health', {}, {})
            first['host']['integration_ready']['panel'] = False
            second = router('GET', '/health', {}, {})
        self.assertEqual(second['host'], {'version': '22.0.368', 'integration_ready': {'panel': True}})
        self.assertEqual(second['scene'], {'scene_epoch': 'original'})
