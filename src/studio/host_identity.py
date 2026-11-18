"""Small host facts collected once on normal GUI registration, never scene work."""
from __future__ import annotations

import importlib
import platform
import sys
from pathlib import Path


def _read(call):
    try:
        return call()
    except Exception:
        return None


def _text(value):
    return value if isinstance(value, str) and 0 < len(value) <= 160 else None


def collect_host_identity(hou, paths, dispatcher, *, modules=None):
    # Called on Houdini's main thread during its existing uiready registration.
    # No scene read, cook, new process, environment dump or credential access.
    if modules is None:
        modules = {name: _read(lambda name=name: importlib.import_module(name))
                   for name in ('PySide6', 'PySide6.QtCore', 'PySide6.QtGui', 'shiboken6')}
    qt, gui = modules.get('PySide6.QtCore'), modules.get('PySide6.QtGui')
    license_value = _read(hou.licenseCategory) if hasattr(hou, 'licenseCategory') else None
    license_name = _read(license_value.name) if callable(getattr(license_value, 'name', None)) else None
    ui = _read(hou.isUIAvailable) if hasattr(hou, 'isUIAvailable') else None
    expected = paths.root / 'houdini/python_panels/big_chicken_studio.pypanel'
    panel_source = panel_ready = None
    try:
        panel = hou.pypanel.interfaceByName('big_chicken_studio')
        if panel is None:
            panel_ready = False  # Successful lookup confirmed that it is absent.
        else:
            panel_source = panel.filePath()
            if isinstance(panel_source, str) and panel_source:
                panel_ready = Path(panel_source).resolve() == expected.resolve()
    except Exception:
        pass  # A failed fact read is Unknown, not proof of a missing integration.
    facts = {
        'version': _text(_read(hou.applicationVersionString)) if hasattr(hou, 'applicationVersionString') else None,
        'application': _text(_read(hou.applicationName)) if hasattr(hou, 'applicationName') else None,
        'application_display_name': _text(_read(lambda: gui.QGuiApplication.applicationDisplayName())),
        'license_category': _text(license_name), 'ui_available': ui if type(ui) is bool else None,
        'python_version': platform.python_version(), 'qt_version': _text(_read(lambda: qt.qVersion())),
        'pyside_version': _text(getattr(modules.get('PySide6'), '__version__', None)),
        'platform': sys.platform, 'machine': platform.machine(),
        'windows_build': _read(lambda: sys.getwindowsversion().build) if sys.platform == 'win32' else None,
        'integration_ready': {'hdefereval': callable(dispatcher), 'panel': panel_ready,
                              'pyside6': all(modules.get(name) is not None for name in
                                            ('PySide6', 'PySide6.QtCore', 'PySide6.QtGui'))},
        'executable': sys.executable, 'panel_source': panel_source,
        'modules': {name: getattr(module, '__file__', None) for name, module in
                    {'studio': sys.modules.get('studio'), 'hou': hou, **modules}.items()},
    }
    from .houdini_compatibility import classify_houdini
    facts['compatibility'] = classify_houdini(facts)
    return facts
