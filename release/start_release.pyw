"""Installed entry: private runtime, selected version, normal platform user roots."""
import ctypes
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
root = Path(__file__).resolve().parents[1]
os.environ['HIA_PROJECT_ROOT'] = str(root)
os.environ['BCS_CODEX_PATH'] = str(root / 'tools/codex/bin/codex.exe')

try:
    from studio.common import AppPaths
    from studio.launcher import launcher_environment
    from studio.__main__ import main
    paths = AppPaths.for_user(root)
    environment = launcher_environment(paths)
    environment['BCS_CODEX_PATH'] = str(root / 'tools/codex/bin/codex.exe')
    os.environ.clear()
    os.environ.update(environment)
    folder = paths.cache('logs')
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'launcher.log').open('a', encoding='utf-8') as log:
        sys.stdout = sys.stderr = log
        try:
            result = main(['launcher'])
        except Exception as error:
            print('Launcher failed:', type(error).__name__)
            result = 1
        finally:
            sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
    if result:
        raise RuntimeError('LAUNCHER_FAILED')
except Exception:
    ctypes.windll.user32.MessageBoxW(None,
        'Studio 未能打开。请关闭此版本的会话后重新安装，或使用上一个可用版本。\n'
        '用户场景和对话记录会保留。', 'Big-Chicken Houdini Studio', 0x10)
