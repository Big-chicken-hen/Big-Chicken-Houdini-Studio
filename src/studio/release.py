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


def build_id(value):
    return value if isinstance(value, str) and re.fullmatch(
        r'\d+\.\d+\.\d+(?:-[a-zA-Z0-9.]+)?-[0-9a-f]{7,40}', value) else None


def local_identity(paths):
    """Read bounded installation metadata once per owner; never hash or probe."""
    manifest = {}
    try:
        with (paths.root / 'release-manifest.json').open('rb') as stream:
            raw = stream.read(2 * 1024 * 1024 + 1)
        if len(raw) <= 2 * 1024 * 1024:
            value = json.loads(raw)
            if isinstance(value, dict):
                manifest = value
    except (OSError, ValueError):
        pass
    commit = manifest.get('source_commit')
    return {'studio_version': version(manifest.get('version')) or __version__,
            'build_id': build_id(manifest.get('build_id')),
            'source_commit': commit if isinstance(commit, str) and re.fullmatch('[0-9a-f]{40}', commit) else None,
            'installation_root': str(paths.root), 'state_root': str(paths.data_root), 'cache_root': str(paths.cache_root)}


def identity_details(identity, *, selected=None, host=None, connected=False):
    """Local, copyable facts only. These paths never enter the diagnostic ZIP."""
    identity, selected = identity or {}, selected or {}
    codex = identity.get('codex') or {}
    source = {'bundled': 'Bundled', 'explicit_external': 'Explicit external',
              'discovered': 'Discovered (development)'}.get(codex.get('source'), 'Unknown')
    compatibility = {'validated': 'Validated', 'untested': 'Untested',
                     'unsupported': 'Unsupported by this release', 'unknown': 'Unknown'}

    def status(facts):
        return compatibility.get((facts.get('compatibility') or {}).get('status'), 'Unknown')

    lines = [f"Studio {identity.get('studio_version') or 'Unknown'}",
             f"Build ID: {identity.get('build_id') or 'Unknown'}",
             f"安装位置: {identity.get('installation_root') or 'Unknown'}",
             f"Codex · {source} · 已确认版本: {codex.get('version') or 'Unknown'}",
             f"Codex 路径: {codex.get('path') or 'Unknown'}",
             f"Houdini · 已选择: {selected.get('version') or 'Unknown'} · {status(selected)}",
             f"Houdini 路径: {selected.get('path') or 'Unknown'}"]
    if connected and host:
        lines.extend([f"Houdini · 正在运行: {host.get('version') or 'Unknown'} · {status(host)}",
                      f"Application: {host.get('application_display_name') or host.get('application') or 'Unknown'} · License: {host.get('license_category') or 'Unknown'}",
                      f"宿主 Python: {host.get('python_version') or 'Unknown'} · Qt: {host.get('qt_version') or 'Unknown'}"])
    else:
        lines.append('Houdini · 正在运行: Unknown（尚未连接）')
    lines.extend([f"用户数据: {identity.get('state_root') or 'Unknown'}",
                  f"临时缓存: {identity.get('cache_root') or 'Unknown'}"])
    return '\n'.join(lines)


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
    host = snapshot.get('host') or {}
    code = failure.get('code') if isinstance(failure, dict) else getattr(failure, 'code', None)
    code = code if isinstance(code, str) and re.fullmatch('[A-Z][A-Z0-9_]{0,63}', code) else None
    commit = manifest.get('source_commit')
    commit = commit if isinstance(commit, str) and re.fullmatch('[0-9a-f]{40}', commit) else None
    allowed_phases = {'checking', 'setup', 'authentication', 'home', 'launching', 'attention',
                      'pending', 'starting', 'runtime_registered', 'target_opened', 'failed', 'unknown'}
    value = {'format': 1, 'studio_version': version(manifest.get('version')) or __version__,
             'build_id': build_id(manifest.get('build_id')),
             'source_commit': commit, 'package_integrity': package, 'windows_version': platform.win32_ver()[1],
             'python_version': platform.python_version(), 'codex_version': version(codex.get('version')),
             'codex_source': codex.get('source') if codex.get('source') in {'bundled', 'explicit_external', 'discovered'} else None,
             'houdini_version': version(houdini.get('version')),
             'houdini_running_version': version(host.get('version')),
             'houdini_compatibility': _compatibility_status(houdini),
             'houdini_running_compatibility': _compatibility_status(host),
             'houdini_application': host.get('application') if host.get('application') in {
                 'houdini', 'houdinifx', 'houdinicore', 'hescape', 'Houdini', 'Houdini FX', 'Houdini Core',
                 'Houdini Indie', 'Houdini Education', 'Houdini Apprentice'} else None,
             'houdini_license_category': host.get('license_category') if host.get('license_category') in {
                 'Commercial', 'Indie', 'Education', 'Apprentice', 'ApprenticeHD'} else None,
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


def _compatibility_status(facts):
    value = (facts.get('compatibility') or {}).get('status')
    return value if value in {'validated', 'untested', 'unsupported', 'unknown'} else None
