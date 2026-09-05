"""Small durable workspace PNG store; no caller-supplied file paths.

Capture frame/resolution evidence follows HIA executor._capture_resolution /
_capture_viewport at 6d9a2d7b606d699fc85bf13586d31aa27455a63b. This store is new:
it does not import HIA or inherit its session-only mapping or quality framework.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import struct
import zlib

from .common import StudioError, atomic_json, new_id

MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_DIMENSION = 2560
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_dimensions(data):
    """Validate PNG structure, CRCs and bounded scanline data before trusting IHDR."""
    def invalid():
        raise StudioError("PNG_INVALID", "Capture is not a complete supported PNG")

    if not data.startswith(PNG_SIGNATURE) or len(data) > MAX_IMAGE_BYTES:
        invalid()
    offset, header, compressed, palette, ended_idat = 8, None, [], False, False
    ended = False
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(data):
            invalid()
        payload = data[offset + 8:end - 4]
        crc = struct.unpack(">I", data[end - 4:end])[0]
        if zlib.crc32(kind + payload) & 0xffffffff != crc:
            invalid()
        if header is None and kind != b"IHDR":
            invalid()
        if kind == b"IHDR":
            if header is not None or length != 13:
                invalid()
            header = struct.unpack(">IIBBBBB", payload)
        elif kind == b"PLTE":
            if compressed or not 0 < length <= 768 or length % 3:
                invalid()
            palette = True
        elif kind == b"IDAT":
            if ended_idat:
                invalid()
            compressed.append(payload)
        elif kind == b"IEND":
            if length or end != len(data):
                invalid()
            ended = True
            break
        elif kind[:1].isupper():  # Unknown critical chunk.
            invalid()
        if compressed and kind != b"IDAT":
            ended_idat = True
        offset = end
    if not ended or header is None or not compressed:
        invalid()
    width, height, depth, color, compression, filtering, interlace = header
    depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
    if (not 0 < width <= MAX_DIMENSION or not 0 < height <= MAX_DIMENSION or
            depth not in depths.get(color, ()) or compression or filtering or interlace not in {0, 1} or
            color == 3 and not palette):
        invalid()
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    passes = [(0, 0, 1, 1)] if interlace == 0 else [
        (0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
        (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2)]
    rows = []
    for x, y, dx, dy in passes:
        columns, count = max(0, (width - x + dx - 1) // dx), max(0, (height - y + dy - 1) // dy)
        if columns:
            rows.extend([1 + (columns * channels * depth + 7) // 8] * count)
    expected = sum(rows)
    try:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(b"".join(compressed), expected + 1)
    except zlib.error:
        invalid()
    if len(raw) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        invalid()
    offset = 0
    for length in rows:
        if raw[offset] > 4:
            invalid()
        offset += length
    return width, height


def capture_resolution(arguments, viewport):
    """Use explicit dimensions or the live viewport aspect, bounded to 2560."""
    if "resolution" in arguments:
        width, height = arguments["resolution"]
        source = "requested"
    else:
        size = viewport.size()
        if (not isinstance(size, (list, tuple)) or len(size) != 4 or
                any(type(v) not in (int, float) for v in size[2:])):
            raise StudioError("VIEWPORT_RESOLUTION_UNAVAILABLE", "Specify resolution; live viewport size is unavailable")
        width, height = size[2:]
        if not 0 < width < float("inf") or not 0 < height < float("inf"):
            raise StudioError("VIEWPORT_RESOLUTION_UNAVAILABLE", "Specify resolution; live viewport size is unavailable")
        scale = min(1.0, MAX_DIMENSION / max(width, height))
        width, height, source = round(width * scale), round(height * scale), "viewport"
    if any(type(v) is not int or not 64 <= v <= MAX_DIMENSION for v in (width, height)):
        raise StudioError("INVALID_ARGUMENTS", "Resolution must remain between 64 and 2560 pixels per dimension")
    return width, height, source


class ArtifactStore:
    """Fixed <workspace>/artifacts/<id>/{image.png,manifest.json} references."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _file(self, artifact_id, filename):
        if not isinstance(artifact_id, str) or re.fullmatch(r"[a-f0-9]{32}", artifact_id) is None:
            raise StudioError("ARTIFACT_NOT_FOUND", "Unknown capture", 404)
        path = self.root / artifact_id / filename
        # Reject redirected directories/files, including links created after capture.
        if path.resolve() != path or path.parent.resolve().parent != self.root:
            raise StudioError("ARTIFACT_PATH_INVALID", "Capture storage was redirected", 409)
        return path

    def allocate(self):
        artifact_id = new_id()
        path = self._file(artifact_id, "image.png")
        path.parent.mkdir(exist_ok=False)
        return artifact_id, path

    def _read_png(self, artifact_id):
        path = self._file(artifact_id, "image.png")
        try:
            with path.open("rb") as stream:
                data = stream.read(MAX_IMAGE_BYTES + 1)
        except OSError as exc:
            raise StudioError("ARTIFACT_NOT_FOUND", "Capture file is unavailable", 404) from exc
        if len(data) > MAX_IMAGE_BYTES:
            raise StudioError("IMAGE_TOO_LARGE", "Capture exceeds 12 MB; request a smaller resolution", 413)
        return data, png_dimensions(data)

    def commit(self, artifact_id, capture, expected_resolution):
        """Register only a valid image; manifest paths are never accepted as input."""
        manifest_path = self._file(artifact_id, "manifest.json")
        if manifest_path.exists():
            raise StudioError("ARTIFACT_ALREADY_COMMITTED", "Capture is already registered", 409)
        data, (width, height) = self._read_png(artifact_id)
        if [width, height] != list(expected_resolution):
            raise StudioError("CAPTURE_RESOLUTION_MISMATCH", "PNG dimensions do not match the requested resolution",
                              actual_resolution=[width, height], requested_resolution=list(expected_resolution))
        manifest = {"version": 1, "artifact_id": artifact_id, "mime_type": "image/png",
                    "width": width, "height": height, "byte_length": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(), "capture": capture}
        # The manifest/receipt must not get ahead of the completed image file.
        with self._file(artifact_id, "image.png").open("rb+") as stream:
            os.fsync(stream.fileno())
        atomic_json(manifest_path, manifest)
        return {key: manifest[key] for key in ("artifact_id", "mime_type", "width", "height", "byte_length")}

    def read(self, artifact_id):
        manifest_path = self._file(artifact_id, "manifest.json")
        try:
            with manifest_path.open("rb") as stream:
                raw = stream.read(16385)
            manifest = json.loads(raw) if len(raw) <= 16384 else None
        except (OSError, ValueError) as exc:
            raise StudioError("ARTIFACT_NOT_FOUND", "Capture manifest is unavailable", 404) from exc
        if (not isinstance(manifest, dict) or manifest.get("version") != 1 or
                manifest.get("artifact_id") != artifact_id or manifest.get("mime_type") != "image/png"):
            raise StudioError("ARTIFACT_INVALID", "Capture manifest is invalid", 409)
        data, dimensions = self._read_png(artifact_id)
        if (dimensions != (manifest.get("width"), manifest.get("height")) or len(data) != manifest.get("byte_length") or
                hashlib.sha256(data).hexdigest() != manifest.get("sha256")):
            raise StudioError("ARTIFACT_CHANGED", "Capture bytes no longer match the persisted reference", 409)
        return data
