"""Assemble an offline, pinned Windows directory package; never touch user state."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
QT_MODULES = {'Core', 'Gui', 'Widgets', 'Network', 'Svg'}


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def destination(root, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
        raise ValueError('Unsafe archive member: ' + name)
    path = root.joinpath(*relative.parts)
    if root.resolve() not in path.resolve().parents:
        raise ValueError('Archive entry escaped its destination')
    return path


def extract_zip(archive, target, include=lambda name: True):
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            if member.is_dir() or not include(member.filename):
                continue
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Symlink in binary archive')
            path = destination(target, member.filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            with source.open(member) as incoming, path.open('xb') as outgoing:
                shutil.copyfileobj(incoming, outgoing)


def pyside_file(name):
    # Ship the binding modules Studio imports, their common Python support,
    # Qt libraries and image/platform plugins. No QML/Designer/Web components.
    parts = PurePosixPath(name).parts
    if '.dist-info' in parts[0]:
        return True
    if parts[0] != 'PySide6':
        return False
    if name.endswith('.py'):
        return True
    if len(parts) == 2:
        leaf = parts[-1]
        return (leaf in {f'Qt{module}.pyd' for module in QT_MODULES}
                or leaf in {f'Qt6{module}.dll' for module in QT_MODULES}
                or leaf == 'pyside6.abi3.dll'
                or leaf.startswith(('concrt', 'msvcp', 'vcruntime', 'vcomp', 'vcamp', 'vccorlib')))
    return name in {'PySide6/plugins/platforms/qwindows.dll', 'PySide6/plugins/platforms/qoffscreen.dll',
                   'PySide6/plugins/imageformats/qgif.dll', 'PySide6/plugins/imageformats/qico.dll',
                   'PySide6/plugins/imageformats/qjpeg.dll', 'PySide6/plugins/imageformats/qsvg.dll',
                   'PySide6/plugins/imageformats/qwebp.dll'}


def git(source, *args):
    return subprocess.check_output(['git', '-C', str(source), *args], text=True, encoding='utf-8').strip()


def build(args):
    source, output, cache = args.source.resolve(), args.output.resolve(), args.inputs.resolve()
    if not any(base / '.runtime' in output.parents for base in (ROOT, source)):
        raise ValueError('Build outputs must stay under a selected checkout .runtime')
    if output.exists():
        raise ValueError('Choose a new build directory; existing artifacts are preserved')
    if git(source, 'status', '--porcelain', '--untracked-files=no'):
        raise ValueError('Commit the source candidate before assembling its package')
    lock = json.loads((ROOT / 'release/windows-inputs.lock.json').read_text(encoding='utf-8'))
    inputs = {}
    for item in lock['sources']:
        path = cache / item['file']
        if not path.is_file() or path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
            raise ValueError('Missing or changed locked build input: ' + item['file'])
        inputs[item['file']] = path
    commit = git(source, 'rev-parse', 'HEAD')
    build_id = lock['studio_version'] + '-' + commit[:12]
    package = output / build_id
    package.mkdir(parents=True)
    names = git(source, 'ls-files', '-z', 'src', 'houdini', 'pyproject.toml', 'README.md', 'LICENSE').split('\0')
    for name in names:
        if not name or name.startswith('src/studio/ui/assets/rain-night-studio.'):
            continue
        src = source / name
        if src.is_symlink() or not src.is_file():
            raise ValueError('Unexpected production source entry')
        dest = destination(package, name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    runtime = package / 'runtime'
    extract_zip(inputs['python-3.13.15-embed-amd64.zip'], runtime)
    site = runtime / 'Lib/site-packages'
    extract_zip(inputs['PySide6_Essentials-6.8.3-cp39-abi3-win_amd64.whl'], site, pyside_file)
    extract_zip(inputs['shiboken6-6.8.3-cp39-abi3-win_amd64.whl'], site)
    (runtime / 'python313._pth').write_text('python313.zip\n.\nLib/site-packages\n../src\nimport site\n', encoding='utf-8')
    codex = package / 'tools/codex'
    prefix = 'package/vendor/x86_64-pc-windows-msvc/'
    with tarfile.open(inputs['codex-0.153.4-win32-x64.tgz']) as archive:
        for member in archive:
            if not member.name.startswith(prefix) or member.isdir():
                continue
            if not member.isfile():
                raise ValueError('Non-file in native Codex package')
            path = destination(codex, member.name[len(prefix):])
            path.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as incoming, path.open('xb') as outgoing:
                shutil.copyfileobj(incoming, outgoing)
    notices = package / 'licenses'
    notices.mkdir()
    for filename in ('CODEX-LICENSE', 'CODEX-NOTICE', 'RIPGREP-LICENSE-MIT', 'RIPGREP-UNLICENSE',
                     'PCRE2-LICENCE', 'RATATUI-0.30.2-LICENSE', 'MSVC-RUNTIME-LICENSE.rtf'):
        shutil.copyfile(inputs[filename], notices / filename)
    shutil.copyfile(runtime / 'LICENSE.txt', notices / 'PYTHON-LICENSE.txt')
    for filename in ('qtbase-everywhere-src-6.8.3.tar.xz', 'qtsvg-everywhere-src-6.8.3.tar.xz',
                     'pyside-setup-everywhere-src-6.8.3.tar.xz', 'qtimageformats-everywhere-src-6.8.3.tar.xz'):
        dest = notices / 'sources' / filename
        dest.parent.mkdir(exist_ok=True)
        shutil.copyfile(inputs[filename], dest)
    shutil.copyfile(ROOT / 'release/THIRD-PARTY-NOTICES.md', notices / 'THIRD-PARTY-NOTICES.md')
    shutil.copyfile(ROOT / 'release/start_release.pyw', runtime / 'start_release.pyw')
    subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                    str(ROOT / 'scripts/build_studio_entry.ps1'), '-Output', str(package / 'Studio.exe')], check=True)
    shutil.copyfile(ROOT / 'release/windows-inputs.lock.json', package / 'build-inputs.json')
    manifest = {'format': 1, 'version': lock['studio_version'], 'build_id': build_id,
                'source_commit': commit, 'builder_commit': git(ROOT, 'rev-parse', 'HEAD'),
                'python': lock['python_version'], 'codex': lock['codex_version'], 'pyside': lock['pyside_version'],
                'target': 'Windows 11 x64 / Houdini FX 22.0.368', 'signed': False,
                'release_acceptance': 'pending',
                'files': {p.relative_to(package).as_posix(): digest(p) for p in sorted(package.rglob('*')) if p.is_file()}}
    (package / 'release-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if args.iscc:
        subprocess.run([str(args.iscc.resolve()), '/Qp', '/DPayload=' + str(package), '/DBuildId=' + build_id,
                        '/DOutput=' + str(output), str(ROOT / 'release/windows.iss')], check=True)
        for installer in output.glob('*.exe'):
            installer.with_suffix('.exe.sha256').write_text(digest(installer) + '  ' + installer.name + '\n', encoding='ascii')
    print(json.dumps({'package': str(package), 'build_id': build_id, 'files': len(manifest['files']),
                      'source_commit': commit, 'release_acceptance': 'pending'}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT)
    parser.add_argument('--inputs', type=Path, required=True, help='Already downloaded, hash-locked build inputs')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--iscc', type=Path, help='Explicit portable Inno Setup compiler')
    build(parser.parse_args())
