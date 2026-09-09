"""R2 keeps query facts/cursors while removing measured mechanical work."""
import copy
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import zipfile

from studio.common import StudioError
from studio.installed_help import HelpReader, installed_help
from studio.lookup import installed_lookup, validate_lookup
from studio.mcp import TOOLS
from studio.observation_results import observation_summary
from studio.tool_schema import LOOKUP_SCHEMA, validate_schema


class EfficiencyTests(unittest.TestCase):
    def test_nested_schema_failure_names_index_field_and_bound_before_queue(self):
        args = {"source": "metadata", "requests": [
            {"kind": "categories"}, {"kind": "type", "category": "Sop", "type_name": "resample", "parameter_limit": 70}]}
        for validator in (lambda: validate_schema(args, LOOKUP_SCHEMA), lambda: validate_lookup(args)):
            with self.assertRaises(StudioError) as caught:
                validator()
            self.assertEqual(caught.exception.details["field"], "arguments.requests[1].parameter_limit")
            self.assertEqual(caught.exception.details["maximum"], 64)
            self.assertIn("maximum=64", caught.exception.message)
        args = {"source": "hom", "symbol": "hou.viewportGuide", "members": True, "limit": 80}
        with self.assertRaises(StudioError) as caught:
            validate_schema(args, LOOKUP_SCHEMA)
        self.assertEqual(caught.exception.details["field"], "arguments.limit")
        self.assertEqual(caught.exception.details["maximum"], 64, "Only metadata search gets the common 80 limit")

    def test_other_union_shapes_remain_strict_and_errors_locate_nested_targets(self):
        execute = next(t['inputSchema'] for t in TOOLS if t['name'] == 'hia_execute_hom')
        args = {"steps": [{"id": "a", "label": "first", "script": "result=1"},
                          {"id": "b", "label": "second", "script": "result=2", "observe_after": [
                              {"view": "parameters", "path": "/obj", "limit": 129}]}]}
        with self.assertRaises(StudioError) as caught:
            validate_schema(args, execute)
        self.assertEqual(caught.exception.details['field'], 'arguments.steps[1].observe_after[0].limit')
        for change in ({"script": "result=0"}, {"steps": args['steps'][:1]}):
            with self.assertRaises(StudioError):
                validate_schema({**args, **change}, execute)

    def types(self):
        counters = {"catalog": 0, "state": 0, "rich": 0}
        types = {}
        def catalog():
            counters['catalog'] += 1
            return types
        category = NS(name=lambda: 'Sop', nodeTypes=catalog)
        def state(value):
            counters['state'] += 1
            return value
        def rich():
            counters['rich'] += 1
            return {'version': '22', 'reason': 'test installed deprecation'}
        for i in range(90):
            name = ('match' if i < 85 else 'unrelated') + str(i).zfill(2)
            types[name] = NS(name=lambda n=name: n, category=lambda: category, description=lambda n=name: n,
                             aliases=lambda: (), hidden=lambda: state(False), deprecated=lambda: state(True),
                             deprecationInfo=rich)
        return NS(nodeTypeCategories=lambda: {'Sop': category}, applicationVersionString=lambda: '22.0.368'), types, counters

    def lookup(self, hou, args):
        return installed_lookup(hou, args, str, lambda exc, code: {'code': code})

    def test_search_compatibility_pages_and_only_returned_matches_get_rich_state(self):
        hou, types, counters = self.types()
        request = {"kind": "search", "category": "Sop", "query": "match", "include_deprecated": True, "include_hidden": True}
        batch = self.lookup(hou, {"source": "metadata", "requests": [request, {**request, "offset": 12, "limit": 2}]})
        self.assertEqual(counters['catalog'], 1)
        self.assertEqual(counters['state'], 85 * 2, "Unrelated types must not read lifecycle state")
        self.assertEqual(counters['rich'], 14, "Detailed deprecation is needed only for returned rows")
        first = batch['requests'][0]
        self.assertEqual((len(first['types']), first['next_offset'], first['total']), (12, 12, 85))
        flat = self.lookup(hou, {k: v for k, v in request.items() if k != 'kind'})
        self.assertEqual(first['types'], flat['types'])
        for args in ({**request, 'limit': 80}, {**request, 'limit': 81}):
            canonical = {'source': 'metadata', 'requests': [args]}
            legacy = {k: v for k, v in args.items() if k != 'kind'}
            if args['limit'] == 80:
                validate_schema(canonical, LOOKUP_SCHEMA)
                validate_schema(legacy, LOOKUP_SCHEMA)
            else:
                for value in (canonical, legacy):
                    with self.assertRaises(StudioError):
                        validate_schema(value, LOOKUP_SCHEMA)
        types.pop('match00')
        changed = self.lookup(hou, {'source': 'metadata', 'requests': [request]})
        self.assertEqual(changed['requests'][0]['total'], 84, 'No cross-request stale installation catalog')

    def test_help_archive_open_and_target_read_reused_only_within_request(self):
        root = Path(__file__).resolve().parents[1] / '.runtime' / 'r2-tests'
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temp:
            root = Path(temp)
            def write(text):
                with zipfile.ZipFile(root/'nodes.zip', 'w') as archive:
                    archive.writestr('sop/test.txt', text)
                    archive.writestr('sop/other.txt', 'other')
            write('complete help text')
            nt = NS(name=lambda: 'test', category=lambda: NS(name=lambda: 'Sop'), embeddedHelp=lambda: '', helpUrl=lambda: '')
            hou = NS(applicationVersionString=lambda: '22.0.368')
            with patch('studio.installed_help.zipfile.ZipFile', wraps=zipfile.ZipFile) as opens:
                with HelpReader() as reader:
                    first = installed_help(hou, nt, {'help_limit': 8}, str, help_root=root,
                                           path_resolver=lambda _: ['/nodes/sop/test'], reader=reader)
                    second = installed_help(hou, nt, {'help_offset': 8}, str, help_root=root,
                                            path_resolver=lambda _: ['/nodes/sop/test'], reader=reader)
                    archive = next(iter(reader.archives.values()))
                    self.assertEqual(first['text'] + second['text'], 'complete help text')
                    self.assertEqual(len(reader.targets), 1)
                    self.assertEqual(opens.call_count, 1)
                self.assertIsNone(archive.fp, 'Request completion closes native archive handle')
            write('updated installed help')
            current = installed_help(hou, nt, {}, str, help_root=root, path_resolver=lambda _: ['/nodes/sop/test'])
            self.assertEqual(current['text'], 'updated installed help')

    def test_summary_builds_only_retained_rows_without_mutating_original_detail(self):
        class Discarded(dict):
            def __deepcopy__(self, memo):
                raise AssertionError('Cloned a row outside the retained page')
        detail = {'requests': [{'index': 0, 'status': 'ok', 'type_name': 'test',
            'parameters': [{'name': 'p' + str(i), 'help': 'x' * 1000} if i < 8 else Discarded(name='p'+str(i), help='x'*1000) for i in range(64)],
            'parameter_page': {'offset': 0, 'total': 64, 'next_offset': None}}]}
        original_page = copy.copy(detail['requests'][0]['parameter_page'])
        result = observation_summary('lookup', detail)
        page = result['requests'][0]
        self.assertEqual(page['parameter_page']['next_offset'], len(page['parameters']))
        self.assertEqual(detail['requests'][0]['parameter_page'], original_page)
        self.assertEqual(len(detail['requests'][0]['parameters']), 64)


if __name__ == '__main__':
    unittest.main()
