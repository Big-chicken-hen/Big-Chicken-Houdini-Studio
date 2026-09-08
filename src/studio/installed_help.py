"""Read one installed help target; no web requests, service, extraction or index."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
import re
from urllib.parse import unquote, urlsplit
import zipfile

from .inspection import optional_call

MAX_HELP_BYTES = 256 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024


class HelpUnavailable(Exception):
    pass


def _inside(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    if path != root and root not in path.parents:
        raise HelpUnavailable("HELP_LOCATION_NOT_ALLOWED")
    return path


def _local_text(path, root):
    path = _inside(path, root)
    if path.stat().st_size > MAX_HELP_BYTES:
        raise HelpUnavailable("HELP_TOO_LARGE")
    with path.open("rb") as stream:
        raw = stream.read(MAX_HELP_BYTES + 1)
    if len(raw) > MAX_HELP_BYTES:
        raise HelpUnavailable("HELP_TOO_LARGE")
    return raw.decode("utf-8-sig")


def _help_paths(node_type):
    # H22's installed mapper was verified in hython. Disable snapping because
    # its default resolver can initialize the full help database/zone.
    from hutil.help.houdini.api import NodePathComponents
    components = NodePathComponents.fromType(node_type)
    versioned = bool(node_type.nameComponents()[-1])
    paths = [str(components.toPath(no_version=not versioned, snap_version=False))]
    order = optional_call(node_type, "namespaceOrder")
    if versioned and order and order[0] == node_type.name():
        paths.append(str(components.toPath(no_version=True, snap_version=False)))
    return paths


def _read_wiki_target(root, target):
    parsed = PurePosixPath(target)
    if not target.startswith("/nodes/") or ".." in parsed.parts or "\\" in target:
        raise HelpUnavailable("HELP_LOCATION_NOT_ALLOWED")
    relative = PurePosixPath(str(parsed).lstrip("/") + ".txt")
    loose = _inside(root / str(relative), root)
    if loose.is_file():
        return _local_text(loose, root), {"kind": "installed_file", "location": relative.as_posix()}
    archive_path = _inside(root / "nodes.zip", root)
    if not archive_path.is_file():
        raise HelpUnavailable("HELP_NOT_INSTALLED")
    if archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise HelpUnavailable("HELP_ARCHIVE_TOO_LARGE")
    # The verified H22 nodes.zip contains sop/box.txt, not nodes/sop/box.txt.
    member = PurePosixPath(*relative.parts[1:]).as_posix()
    with zipfile.ZipFile(archive_path) as archive:
        try:
            info = archive.getinfo(member)
        except KeyError:
            raise HelpUnavailable("HELP_TARGET_MISSING") from None
        if info.file_size > MAX_HELP_BYTES:
            raise HelpUnavailable("HELP_TOO_LARGE")
        with archive.open(info) as stream:
            raw = stream.read(MAX_HELP_BYTES + 1)
        if len(raw) > MAX_HELP_BYTES:
            raise HelpUnavailable("HELP_TOO_LARGE")
    return raw.decode("utf-8-sig"), {"kind": "installed_archive", "archive": "nodes.zip", "member": member}


def installed_help(hou, node_type, request, redact, *, help_root=None, path_resolver=None):
    base = {"available": False, "installation_version": hou.applicationVersionString(),
            "document_version": None, "version_status": "not_declared", "format": "source_text"}
    try:
        definition = optional_call(node_type, "definition")
        sections = optional_call(definition, "sections")
        section = sections.get("Help") if isinstance(sections, dict) else None
        size = optional_call(section, "size")
        if type(size) is int and size > MAX_HELP_BYTES:
            raise HelpUnavailable("HELP_TOO_LARGE")
        text = optional_call(node_type, "embeddedHelp")
        provenance = {"kind": "embedded_help", "type": node_type.name(), "category": node_type.category().name()}
        if not text:
            text = None
            root = Path(help_root if help_root is not None else hou.text.expandString("$HH") + "/help").resolve()
            declared = optional_call(node_type, "helpUrl") or ""
            url = urlsplit(declared)
            if url.scheme in {"http", "https"} or declared.startswith("//"):
                raise HelpUnavailable("EXTERNAL_HELP_NOT_READ")
            if declared and url.scheme == "opdef":
                expected = "/" + node_type.category().name() + "/" + node_type.name()
                if unquote(url.path) != expected or not isinstance(sections, dict):
                    raise HelpUnavailable("HELP_LOCATION_NOT_ALLOWED")
                section_name = unquote(url.query)
                section = sections.get(section_name)
                size = optional_call(section, "size")
                if type(size) is not int or size > MAX_HELP_BYTES:
                    raise HelpUnavailable("HELP_SECTION_UNAVAILABLE")
                text = optional_call(section, "contents")
                provenance = {"kind": "hda_section", "type": node_type.name(), "section": section_name}
            elif declared and url.scheme not in {"operator", "op"}:
                if url.scheme not in {"", "file"} or url.netloc:
                    raise HelpUnavailable("HELP_LOCATION_NOT_ALLOWED")
                target = unquote(url.path) if url.scheme == "file" else declared
                if re.match(r"^/[A-Za-z]:/", target):
                    target = target[1:]
                target = _inside(root / target, root)
                if target.suffix.casefold() not in {".txt", ".html", ".md"}:
                    raise HelpUnavailable("HELP_LOCATION_NOT_ALLOWED")
                text = _local_text(target, root)
                provenance = {"kind": "installed_file", "location": target.relative_to(root).as_posix()}
            else:
                last_error = "HELP_TARGET_MISSING"
                for target in (path_resolver or _help_paths)(node_type):
                    try:
                        text, provenance = _read_wiki_target(root, target)
                        provenance["target"] = target
                        break
                    except HelpUnavailable as exc:
                        last_error = str(exc)
                        if last_error not in {"HELP_TARGET_MISSING", "HELP_NOT_INSTALLED"}:
                            raise
                if text is None:
                    raise HelpUnavailable(last_error)
        if not isinstance(text, str) or not text:
            raise HelpUnavailable("HELP_CONTENT_UNAVAILABLE")
        if len(text.encode("utf-8")) > MAX_HELP_BYTES:
            raise HelpUnavailable("HELP_TOO_LARGE")
        text = redact(text)  # Redact the complete bounded source before paging.
        declared_version = re.search(r"(?m)^#houdini_version:\s*([^\r\n]{1,80})", text)
        if declared_version:
            value = declared_version.group(1).strip()
            base.update(document_version=value, version_status="matches_installation" if
                        value.split(".")[:2] == base["installation_version"].split(".")[:2] else "different_version")
        offset, limit = request.get("help_offset", 0), request.get("help_limit", 2048)
        page = text[offset:offset + limit]
        end = offset + len(page)
        return {**base, "available": True, "provenance": provenance, "text": page, "offset": offset,
                "total_characters": len(text), "truncated": end < len(text),
                "next_offset": end if end < len(text) else None,
                "continuation": "Repeat the same type request with help_offset=next_offset"}
    except HelpUnavailable as exc:
        return {**base, "reason": str(exc)}
    except (ImportError, AttributeError):
        return {**base, "reason": "INSTALLED_HELP_RESOLVER_UNAVAILABLE"}
    except Exception:
        # Help is optional even when an installed category's native resolver or
        # HDA reader raises an implementation-specific exception. No raw paths.
        return {**base, "reason": "HELP_READ_FAILED"}
