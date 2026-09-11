"""R4-HELP-1: inspect an existing Houdini help pane without initializing Qt UI.

Run from the real Houdini Python Shell, after the owner opens the help pane:
    import runpy; runpy.run_path(r'E:\\Big-Chicken-Houdini-Studio\\scripts\\inspect_houdini_help.py').get('capture')('studio')
Use 'native' for the same help operation in a directly started Houdini.
This script is a development diagnostic; it is not loaded by Studio.
"""
from collections import deque
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit, urlunsplit
import uuid


ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT_FIELDS = (
    'PATH', 'HFS', 'HOUDINI_USER_PREF_DIR', 'HOUDINI_PATH', 'HOUDINI_PACKAGE_DIR',
    'HOUDINI_OTLSCAN_PATH', 'HOUDINI_OTL_PATH', 'HOUDINI_OPLIBRARIES_PATH', 'HOUDINI_DSO_PATH',
    'TEMP', 'TMP', 'TMPDIR', 'HOUDINI_TEMP_DIR', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME',
    'XDG_DATA_HOME', 'PYTHONPATH', 'PYTHONHOME', 'PYTHONNOUSERSITE', 'QT_PLUGIN_PATH',
    'QML_IMPORT_PATH', 'QML2_IMPORT_PATH', 'QTWEBENGINEPROCESS_PATH',
    'QTWEBENGINE_RESOURCES_PATH', 'QTWEBENGINE_LOCALES_PATH',
    'QML_IMPORT_TRACE', 'QT_DEBUG_PLUGINS', 'QT_LOGGING_RULES', 'QT_FORCE_STDERR_LOGGING',
)
QT_PATHS = ('PrefixPath', 'LibraryExecutablesPath', 'DataPath', 'PluginsPath',
            'QmlImportsPath', 'TranslationsPath')


def unavailable(reason):
    return {'available': False, 'reason': reason}


def safe_url(value):
    """Keep diagnostic locations, never credentials, query strings or fragments."""
    try:
        parts = urlsplit(str(value))
        return urlunsplit((parts.scheme, parts.netloc.rsplit('@', 1)[-1], parts.path, '', ''))
    except ValueError:
        return '[unavailable URL]'


def safe_text(value, limit=2000):
    text = re.sub(r'\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s<>\"\']+',
                  lambda match: safe_url(match.group()), str(value))
    return text if limit is None else text[:limit]


def read(call):
    try:
        return call()
    except Exception as error:
        return unavailable(type(error).__name__)


def quick_facts(widget, qml):
    result = {
        'status': str(widget.status()),
        'source': safe_url(widget.source().toString()),
        'errors': [safe_text(error.toString()) for error in widget.errors()[:12]],
        'engine': unavailable('No existing QML root/binding; no engine created'),
    }
    # Qt 6.8.3 engine() and rootContext() call ensureEngine(): avoid both.
    # rootObject() only returns the existing root. qmlEngine(root) reads its
    # existing association and never constructs a replacement QQmlEngine.
    root = widget.rootObject()
    result['has_root_object'] = root is not None
    if root is not None and qml is not None:
        engine = qml.qmlEngine(root)
        if engine is not None:
            result['engine'] = {'available': True, 'source': 'qmlEngine(existing rootObject)',
                                'import_paths': engine.importPathList(),
                                'plugin_paths': engine.pluginPathList()}
    return result


def help_window_facts(pane, qtwidgets, modules):
    """A bounded subtree only after HOM proves the window contains just this help tab."""
    floating = pane.floatingPanel()
    if floating is None or tuple(floating.paneTabs()) != (pane,):
        return unavailable('Help is embedded or shares a window; no global/window-wide scan performed')
    window = pane.qtParentWindow()  # Documented HOM QWidget return; no raw pointer access.
    if not isinstance(window, qtwidgets.QWidget):
        return unavailable('HOM did not return a supported QWidget')
    quick_module = modules.get('PySide6.QtQuickWidgets')
    qml = modules.get('PySide6.QtQml')
    result = {'available': True, 'scope': 'single-help floating window',
              'visible': window.isVisible(), 'quick_widgets': [], 'visited': 0,
              'truncated': False,
              'navigation': unavailable('No read-only HelpBrowser navigation getter; owner screenshot required')}
    pending = deque([(window, 0)])
    while pending and result['visited'] < 192:
        widget, depth = pending.popleft()
        result['visited'] += 1
        if quick_module is not None and isinstance(widget, quick_module.QQuickWidget):
            result['quick_widgets'].append(read(lambda: quick_facts(widget, qml)))
            continue  # Never descend into the QML object graph.
        children = [child for child in widget.children() if isinstance(child, qtwidgets.QWidget)]
        if depth >= 10:
            result['truncated'] |= bool(children)
            continue
        remaining = 192 - result['visited'] - len(pending)
        result['truncated'] |= len(children) > remaining
        pending.extend((child, depth + 1) for child in children[:max(0, remaining)])
    result['truncated'] |= bool(pending)
    if not result['quick_widgets']:
        result['carrier'] = unavailable('No safely typed existing QQuickWidget in this bounded scope')
    return result


def collect(hou, qtcore, qtwidgets, modules, *, case, pane_name=None):
    result = {'schema': 1, 'issue': 'R4-HELP-1', 'owner_label': case,
              'utc': datetime.now(timezone.utc).isoformat(), 'pid': os.getpid(),
              'status': 'unavailable'}
    app = qtwidgets.QApplication.instance()
    if app is None or qtcore.QThread.currentThread() != app.thread():
        result['reason'] = 'Requires the existing Houdini GUI main thread; no dispatch or GUI creation'
        return result
    if not hou.isUIAvailable():
        result['reason'] = 'Houdini GUI unavailable'
        return result
    result['host'] = {'executable': app.applicationFilePath(), 'python_executable': sys.executable,
                      'version': hou.applicationVersionString(), 'cwd': os.getcwd(),
                      'preferences': hou.getenv('HOUDINI_USER_PREF_DIR'),
                      'runtime_module_loaded': 'studio.runtime_server' in modules,
                      'panel_module_loaded': 'studio.ui.panel' in modules,
                      'module_files': {name: getattr(modules.get(name), '__file__', None)
                                       for name in ('hou', 'PySide6.QtCore', 'studio',
                                                    'studio.runtime_server', 'studio.ui.panel')}}
    result['environment'] = {name: safe_text(os.environ[name], limit=None) for name in ENVIRONMENT_FIELDS
                             if name in os.environ}
    result['qt'] = {'version': qtcore.qVersion(), 'library_paths': app.libraryPaths(),
                    'paths': {name: qtcore.QLibraryInfo.path(getattr(qtcore.QLibraryInfo, name))
                              for name in QT_PATHS}}
    # HOM pane enumeration is limited to HelpBrowser; no QApplication.allWidgets(),
    # topLevelWidgets(), unknown getters, pointer wrapping or global QObject scans.
    panes = []
    for index in range(8):
        pane = hou.ui.paneTabOfType(hou.paneTabType.HelpBrowser, index)
        if pane is None:
            break
        panes.append(pane)
    result['help_candidates'] = [pane.name() for pane in panes]
    selected = [pane for pane in panes if pane_name is None or pane.name() == pane_name]
    if len(selected) != 1:
        result['reason'] = 'Expected one existing HelpBrowser; specify its exact pane_name if ambiguous'
        return result
    pane = selected[0]
    result['help'] = {'name': pane.name(), 'type': 'HelpBrowser', 'current_tab': pane.isCurrentTab(),
                      'floating': pane.isFloating(), 'url': safe_url(pane.url()),
                      'home_page': safe_url(pane.homePage()), 'size': list(pane.size()),
                      'window': read(lambda: help_window_facts(pane, qtwidgets, modules))}
    result['status'] = 'captured'  # A snapshot, never an assertion that help works.
    return result


def capture(case='unlabelled', pane_name=None):
    if case not in {'native', 'studio', 'payload', 'unlabelled'}:
        raise ValueError('Use native, studio or payload for the owner-observed launch path')
    modules = sys.modules
    names = ('hou', 'PySide6.QtCore', 'PySide6.QtWidgets')
    if any(modules.get(name) is None for name in names):
        raise RuntimeError('Run inside the real Houdini GUI; this script never imports/initializes a host or Qt')
    def snapshot():
        return collect(*(modules[name] for name in names), modules, case=case, pane_name=pane_name)

    app = modules['PySide6.QtWidgets'].QApplication.instance()
    if app is None or modules['PySide6.QtCore'].QThread.currentThread() == app.thread():
        result = snapshot()  # Never block the GUI thread waiting for its own event loop.
    else:
        # Python Shell runs on a worker. Dispatch this one bounded read through
        # Houdini; collect still checks the actual callback's thread.
        import hdefereval
        result = hdefereval.executeInMainThreadWithResult(snapshot)
    directory = ROOT / '.runtime/maintenance/help-browser-20260911'
    directory.resolve().relative_to((ROOT / '.runtime').resolve())
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f'{case}-{os.getpid()}-{uuid.uuid4().hex[:10]}.json'
    with target.open('x', encoding='utf-8') as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
    print('R4-HELP-1 snapshot: ' + str(target))
    return str(target)
