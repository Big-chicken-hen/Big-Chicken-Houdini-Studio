"""Window-local Shell identity; no Python, Houdini or global taskbar changes."""
from __future__ import annotations

import ctypes
from pathlib import Path
import sys
import uuid

from PySide6 import QtGui

from .launcher_palette import ARTWORK

APP_USER_MODEL_ID = 'BigChicken.HoudiniStudio'


class _Guid(ctypes.Structure):
    _fields_ = [('data1', ctypes.c_uint32), ('data2', ctypes.c_uint16),
                ('data3', ctypes.c_uint16), ('data4', ctypes.c_ubyte * 8)]


class _PropertyKey(ctypes.Structure):
    _fields_ = [('fmtid', _Guid), ('pid', ctypes.c_uint32)]


class _CountedPointer(ctypes.Structure):
    _fields_ = [('count', ctypes.c_uint32), ('pointer', ctypes.c_void_p)]


class _VariantValue(ctypes.Union):
    _fields_ = [('pointer', ctypes.c_void_p), ('counted', _CountedPointer), ('integer', ctypes.c_int64)]


class _PropVariant(ctypes.Structure):
    _fields_ = [('vt', ctypes.c_uint16), ('reserved', ctypes.c_uint16 * 3), ('value', _VariantValue)]


def _guid(value):
    return _Guid.from_buffer_copy(uuid.UUID(value).bytes_le)


def _set_window_properties(hwnd, values):
    store = ctypes.c_void_p()
    iid = _guid('886d8eeb-8cf2-4446-8d02-cdba1dbdcf99')  # IPropertyStore
    getter = ctypes.WinDLL('shell32').SHGetPropertyStoreForWindow
    getter.argtypes = (ctypes.c_void_p, ctypes.POINTER(_Guid), ctypes.POINTER(ctypes.c_void_p))
    getter.restype = ctypes.c_long
    if getter(hwnd, ctypes.byref(iid), ctypes.byref(store)) < 0:
        return False
    table = ctypes.cast(store, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    setter = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(_PropertyKey),
                               ctypes.POINTER(_PropVariant))(table[6])
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(table[2])
    success = True
    try:
        for pid, text in values:
            key = _PropertyKey(_guid('9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3'), pid)
            variant = _PropVariant()  # VT_EMPTY removes an owned window property.
            if text is not None:
                buffer = ctypes.create_unicode_buffer(text)
                variant.vt = 31  # VT_LPWSTR; SetValue copies this borrowed string.
                variant.value.pointer = ctypes.cast(buffer, ctypes.c_void_p)
            success = (setter(store, ctypes.byref(key), ctypes.byref(variant)) >= 0) and success
        return success
    finally:
        release(store)


def set_launcher_taskbar(window, root):
    if sys.platform != 'win32' or QtGui.QGuiApplication.platformName() != 'windows':
        return False
    entry, icon = Path(root) / 'Studio.exe', ARTWORK / 'studio.ico'
    if not entry.is_file() or not icon.is_file():
        return False
    try:
        hwnd = int(window.winId())
        # Relaunch metadata precedes the explicit ID so Explorer sees one identity.
        success = _set_window_properties(hwnd, ((2, f'"{entry}"'), (3, f'{icon},0'),
                                               (4, window.windowTitle()), (5, APP_USER_MODEL_ID)))
        if not success:
            _set_window_properties(hwnd, ((pid, None) for pid in (2, 3, 4, 5)))
        return success
    except (AttributeError, OSError):
        return False


def clear_launcher_taskbar(window):
    if sys.platform != 'win32' or QtGui.QGuiApplication.platformName() != 'windows':
        return
    try:
        # Shell-owned copies must be released before the HWND closes.
        _set_window_properties(int(window.winId()), ((pid, None) for pid in (2, 3, 4, 5)))
    except (AttributeError, OSError):
        pass
