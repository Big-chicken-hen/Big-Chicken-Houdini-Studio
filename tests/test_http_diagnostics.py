"""Local diagnostic opt-in, expiry, rotation and bounded route cardinality."""
import os
from pathlib import Path
import tempfile
import time
import unittest

from studio.common import AppPaths
from studio.http_diagnostics import HttpDiagnostics, route_label


class HttpDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        temporary = root / '.runtime' / 'tests'
        temporary.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temporary)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.paths = AppPaths(root, data_root=self.directory / 'state', cache_root=self.directory / 'cache')

    def test_default_off_creates_nothing_and_stale_opt_in_does_not_reenable(self):
        self.assertIsNone(HttpDiagnostics.enabled(self.paths))
        self.assertFalse(self.paths.cache_root.exists())
        marker = self.paths.cache('diagnostics', 'http-trace.enabled')
        marker.parent.mkdir(parents=True)
        marker.touch()
        old = time.time() - HttpDiagnostics.session_seconds - 1
        os.utime(marker, (old, old))
        self.assertIsNone(HttpDiagnostics.enabled(self.paths))
        self.assertEqual(list(marker.parent.iterdir()), [marker])
        marker.touch()
        trace = HttpDiagnostics.enabled(self.paths)
        self.assertIsNotNone(trace)
        self.addCleanup(trace.handler.close)
        self.assertIs(HttpDiagnostics.enabled(self.paths), trace)

    def test_rotation_is_bounded_and_expiry_stops_writes(self):
        trace = HttpDiagnostics(self.directory, max_bytes=2048)
        self.addCleanup(trace.handler.close)
        for index in range(120):
            route = route_label('/operations/' + str(index) + '?text=private')
            trace.started(route)
            trace.finished({'route': route, 'phase': 'connect', 'request_id': index},
                           failed=True, cancelled=False)
        files = sorted(self.directory.glob('panel-http-*'))
        self.assertEqual(len(files), 2)
        self.assertTrue(all(path.stat().st_size <= 2048 for path in files))
        before = [path.read_bytes() for path in files]
        trace.expires_at = time.time() - 1
        trace.started('/state')
        trace.finished({'route': '/state', 'phase': 'connect'}, failed=True, cancelled=False)
        self.assertEqual(before, [path.read_bytes() for path in files])
        self.assertEqual(trace.counters['/operations/<id>']['inflight'], 0)
        self.assertTrue(all(b'private' not in data for data in before))


if __name__ == '__main__':
    unittest.main()
