"""Installed-version lifetime and explicit, whitelisted diagnostic export."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import zipfile

from . import __version__
from .common import StudioError, inside

_lease = None


def installed_houdini_version(executable):
    """Read the selected Windows executable's version resource, without a probe."""
    if os.name != 'nt':
        return None
    from ctypes import wintypes
    library = ctypes.WinDLL('version', use_last_error=True)
    library.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    library.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    size = library.GetFileVersionInfoSizeW(str(executable), None)
    if not 0 < size <= 1024 * 1024:
        return None
    data = ctypes.create_string_buffer(size)
    library.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    if not library.GetFileVersionInfoW(str(executable), 0, size, data):
        return None
    pointer, length = ctypes.c_void_p(), wintypes.UINT()
    library.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR,
                                     ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
    if not library.VerQueryValueW(data, '\\', ctypes.byref(pointer), ctypes.byref(length)) or length.value < 52:
        return None
    fixed = ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD * 13)).contents
    if fixed[0] != 0xFEEF04BD:
        return None
    # SideFX records 22.0.368 as FileVersion 22,0,0,368.
    return f'{fixed[2] >> 16}.{fixed[2] & 65535}.{fixed[3] & 65535}' if fixed[3] >> 16 == 0 else None


def hold_installed_version(root):
    """Every packaged helper and Houdini runtime holds the installer mutex."""
    global _lease
    if os.name != 'nt' or _lease is not None or not (root / 'release-manifest.json').is_file():
        return
    from ctypes import wintypes
    create = ctypes.WinDLL('kernel32', use_last_error=True).CreateMutexW
    create.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    create.restype = wintypes.HANDLE
    _lease = create(None, False, 'Local\\BigChickenStudio.ReleaseInUse')
    if not _lease:
        raise StudioError('INSTALLATION_LEASE_FAILED', '无法确认安装版本正在使用，请重新打开 Studio。')
    # Windows releases this process-owned handle at process exit. Do not make
    # the installer depend on saved PIDs or try to close another user's GUI.


def version(value):
    return value if isinstance(value, str) and re.fullmatch(r'\d+\.\d+(?:\.\d+)?(?:-[a-zA-Z0-9.]+)?', value) else None


def integrity(root):
    manifest_path = root / 'release-manifest.json'
    if not manifest_path.is_file():
        return {}, {'status': 'development_checkout', 'checked_files': 0}
    if manifest_path.stat().st_size > 2 * 1024 * 1024:
        raise StudioError('MANIFEST_INVALID', '安装清单过大，请使用原始安装包。')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    files = manifest.get('files', {})
    if not isinstance(files, dict) or len(files) > 5000:
        raise StudioError('MANIFEST_INVALID', '安装清单无效。')
    missing, changed, checked, total = 0, 0, 0, 0
    for relative, expected in files.items():
        if not isinstance(relative, str) or Path(relative).is_absolute() or ':' in relative:
            raise StudioError('MANIFEST_INVALID', '安装清单包含无效路径。')
        path = inside(root / relative, root)
        if not path.is_file():
            missing += 1
            continue
        total += path.stat().st_size
        if total > 2 * 1024 ** 3:
            raise StudioError('MANIFEST_INVALID', '安装校验超过大小限制。')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        changed += digest.hexdigest() != expected
        checked += 1
    return manifest, {'status': 'mismatch' if missing or changed else 'matched',
                      'checked_files': checked, 'missing_files': missing, 'changed_files': changed}


def export_diagnostics(paths, target, snapshot, *, failure=None, phase=None):
    """No logs, chat, scripts, geometry, credentials, URL or directory scanning."""
    manifest, package = integrity(paths.root)
    account, codex, houdini = (snapshot.get(key) or {} for key in ('account', 'codex', 'houdini'))
    code = failure.get('code') if isinstance(failure, dict) else getattr(failure, 'code', None)
    code = code if isinstance(code, str) and re.fullmatch('[A-Z][A-Z0-9_]{0,63}', code) else None
    commit = manifest.get('source_commit')
    commit = commit if isinstance(commit, str) and re.fullmatch('[0-9a-f]{40}', commit) else None
    allowed_phases = {'checking', 'setup', 'authentication', 'home', 'launching', 'attention',
                      'pending', 'starting', 'runtime_registered', 'target_opened', 'failed', 'unknown'}
    value = {'format': 1, 'studio_version': version(manifest.get('version')) or __version__,
             'source_commit': commit, 'package_integrity': package, 'windows_version': platform.win32_ver()[1],
             'python_version': platform.python_version(), 'codex_version': version(codex.get('version')),
             'houdini_version': version(houdini.get('version')),
             'codex_verified': codex.get('state') == 'ready', 'houdini_found': houdini.get('state') == 'found',
             'account_confirmed': account.get('status') == 'signed_in' and account.get('action_unknown') is not True,
             'failure_code': code, 'phase': phase if phase in allowed_phases else None,
             'timings': None, 'tool_counts': None,
             'scope': 'Whitelisted installation and current launcher facts; no chat, credentials or user artifacts'}
    target = Path(target)
    if not target.is_absolute() or target.suffix.lower() != '.zip':
        raise StudioError('DIAGNOSTIC_PATH_INVALID', '请选择一个新的 ZIP 文件。')
    with target.open('xb') as stream, zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('diagnostics.json', json.dumps(value, ensure_ascii=False, indent=2))
    return str(target)
