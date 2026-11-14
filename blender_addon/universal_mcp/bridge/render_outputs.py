"""Read-only verification of registered still-render artifacts, stdlib only.

No caller-supplied file paths. Receipts are observational IDs, not approvals.
"""
from collections import OrderedDict
import hashlib
import os
from pathlib import Path
import re
import secrets
import struct
import threading
import time
import zlib

MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_DECODED_BYTES = 1024 * 1024 * 1024
RECEIPT_TTL = 3600
RECEIPT_LIMIT = 1024
_receipts = OrderedDict()
_lock = threading.Lock()


def validate_render_id(params):
    if not isinstance(params, dict) or set(params) != {"render_id"} or not isinstance(params["render_id"], str) or not re.fullmatch(r"[0-9a-f]{32}", params["render_id"]):
        raise ValueError("inspect_render_output accepts only a 32-character lowercase hexadecimal render_id")
    return params["render_id"]


def file_signature(path):
    try:
        info = os.stat(path)
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    except FileNotFoundError:
        return None


def _png(path):
    decoded = 0; expected = None; row_bytes = None; header = None
    inflater = zlib.decompressobj(); digest = hashlib.sha256(); saw_idat = False; ended = False
    with open(path, "rb") as stream:
        if stream.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ValueError("Render output has no valid PNG signature")
        while not ended:
            block = stream.read(8)
            if len(block) != 8:
                raise ValueError("Truncated PNG chunk")
            length, kind = struct.unpack(">I4s", block)
            if length > MAX_FILE_BYTES:
                raise ValueError("PNG chunk exceeds inspection budget")
            crc = zlib.crc32(kind); remaining = length; content = b""
            if header is None and kind != b"IHDR":
                raise ValueError("PNG must start with IHDR")
            while remaining:
                piece = stream.read(min(65536, remaining))
                if not piece:
                    raise ValueError("Truncated PNG chunk data")
                remaining -= len(piece); crc = zlib.crc32(piece, crc)
                if kind == b"IHDR":
                    content += piece
                    if len(content) > 13:
                        raise ValueError("Invalid PNG IHDR")
                if kind == b"IDAT":
                    saw_idat = True
                    if expected is None:
                        raise ValueError("Missing PNG dimensions")
                    pending = piece
                    while pending:
                        output = inflater.decompress(pending, 65536)
                        pending = inflater.unconsumed_tail
                        if decoded + len(output) > expected:
                            raise ValueError("PNG decoded size exceeds expected dimensions")
                        offset = (-decoded) % row_bytes
                        while offset < len(output):
                            if output[offset] > 4:
                                raise ValueError("Invalid PNG row filter")
                            offset += row_bytes
                        decoded += len(output); digest.update(output)
                        if inflater.unused_data:
                            raise ValueError("Unexpected data after PNG compressed stream")
            checksum = stream.read(4)
            if len(checksum) != 4 or struct.unpack(">I", checksum)[0] != crc & 0xffffffff:
                raise ValueError("PNG CRC verification failed")
            if kind == b"IHDR":
                if header is not None or length != 13:
                    raise ValueError("Invalid duplicate PNG header")
                width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", content)
                channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color)
                if not width or not height or depth not in (8, 16) or channels is None or compression or filtering or interlace:
                    raise ValueError("Unsupported PNG encoding for render inspection")
                row_bytes = 1 + width * channels * depth // 8
                expected = row_bytes * height
                if expected > MAX_DECODED_BYTES:
                    raise ValueError("PNG exceeds decoded inspection budget")
                header = {"width": width, "height": height, "bit_depth": depth, "color_type": color}
            elif kind == b"IEND":
                if length or stream.read(1):
                    raise ValueError("Unexpected PNG trailing data")
                ended = True
        if not saw_idat or not inflater.eof or decoded != expected:
            raise ValueError("PNG image data is incomplete")
    return {**header, "filtered_scanlines_sha256": digest.hexdigest(), "png_structure_verified": True}


def _snapshot(path, file_format):
    canonical = str(Path(path).resolve(strict=True)); before = file_signature(canonical)
    if before is None or not os.path.isfile(canonical) or not 0 < before[2] <= MAX_FILE_BYTES:
        raise ValueError("Render output missing, empty or exceeds inspection budget")
    digest = hashlib.sha256()
    with open(canonical, "rb") as stream:
        while piece := stream.read(65536):
            digest.update(piece)
    image = _png(canonical) if file_format == "PNG" else {"png_structure_verified": False}
    if file_signature(canonical) != before:
        raise ValueError("Render output changed during inspection")
    return {"path": canonical, "signature": list(before), "size_bytes": before[2], "sha256": digest.hexdigest(), **image}


def record_render_output(path, width, height, file_format, frame, camera):
    snapshot = _snapshot(path, file_format)
    if file_format == "PNG" and (snapshot["width"], snapshot["height"]) != (width, height):
        raise ValueError("Rendered PNG dimensions do not match actual render settings")
    identifier = secrets.token_hex(16)
    entry = {"render_id": identifier, "file_format": file_format, "width": width, "height": height,
             "frame": frame, "camera": camera, "artifact": snapshot, "recorded_at": time.time()}
    with _lock:
        _receipts[identifier] = (time.monotonic(), entry)
        while len(_receipts) > RECEIPT_LIMIT:
            _receipts.popitem(last=False)
    return identifier


def handle_inspect_render_output(bpy_module=None, params=None):
    identifier = validate_render_id(params)
    with _lock:
        found = _receipts.get(identifier)
        if found is None:
            raise ValueError("Render receipt not found; the bridge may have reloaded or evicted it")
        created, entry = found
        if time.monotonic() - created >= RECEIPT_TTL - 1e-6:
            del _receipts[identifier]
            raise ValueError("Render receipt expired; no current artifact verification is available")
    artifact = entry["artifact"]
    if str(Path(artifact["path"]).resolve()) != artifact["path"]:
        raise ValueError("Registered render path changed")
    actual = _snapshot(artifact["path"], entry["file_format"])
    if actual != artifact:
        raise ValueError("Render output changed since completion; receipt is not verified")
    return {"success": True, "verified": True, **entry, "artifact": actual}
