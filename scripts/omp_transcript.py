"""Read oh-my-pi JSONL session transcripts for MindIE capture.

[Role]
Projects visible user and assistant text from OMP session JSONL into the incremental
transcript adapter contract consumed by `mindie_knowledge`.

[Invariants]
- Reads only the selected transcript file and accepts only the requested session.
- Uses persisted file identity checks so replacement or truncation never rereads old data.
- Returns bounded UTF-8 text and leaves secret/path redaction to the shared engine.

[Timeouts & Locks]
- One bounded sequential file scan with no locks or child processes.

[Side-Effect Policy]
- Read-only. Writes no files or environment state.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any, BinaryIO

_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_MAX_SCAN_BYTES = 16 * 1024 * 1024
_MAX_HEADER_BYTES = 1024 * 1024
_ANCHOR_BYTES = 512
_TITLE_SLOT_BYTES = 256
_TITLE_PREFIX = b'{"type":"title","v":1,"title":'


@dataclass(frozen=True)
class FileIdentity:
    path: str
    dev: int
    ino: int
    size: int
    mtime_ns: int
    anchor_len: int = 0
    anchor_digest: str = ""
    anchor_offset: int = 0
    content_digest: str = ""

    def serialize(self) -> str:
        return json.dumps(self.__dict__, sort_keys=True, separators=(",", ":"))

    @classmethod
    def unserialize(cls, payload: Mapping[str, Any] | str, path: str | Path | None = None) -> "FileIdentity | None":
        try:
            data = json.loads(payload) if isinstance(payload, str) else dict(payload)
            if not isinstance(data, dict):
                return None
            raw_path = path or data.get("path")
            values = {key: data[key] for key in (
                "dev", "ino", "size", "mtime_ns", "anchor_len", "anchor_digest",
                "anchor_offset", "content_digest",
            )}
            if not isinstance(raw_path, (str, Path)):
                return None
            return cls(str(Path(raw_path).resolve()), **values)
        except (KeyError, TypeError, ValueError, OSError):
            return None


def _identify(path: Path, stream: BinaryIO) -> FileIdentity:
    stat = os.fstat(stream.fileno())
    prefix = stream.read(min(stat.st_size, _TITLE_SLOT_BYTES + _ANCHOR_BYTES))
    has_title_slot = prefix.startswith(_TITLE_PREFIX) and prefix.find(b"\n") == _TITLE_SLOT_BYTES - 1
    offset = _TITLE_SLOT_BYTES if has_title_slot else 0
    content = prefix[offset:offset + _ANCHOR_BYTES]
    content_digest = hashlib.sha256(content).hexdigest()
    # The shared cursor hashes a raw prefix. Verify the immutable bytes after the mutable title separately.
    anchor_len = len(_TITLE_PREFIX) if has_title_slot else len(content)
    anchor_digest = hashlib.sha256(_TITLE_PREFIX).hexdigest() if has_title_slot else content_digest
    return FileIdentity(str(path), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns,
                        anchor_len, anchor_digest, offset, content_digest)


def identify(path: str | Path) -> FileIdentity | None:
    try:
        selected = Path(path).resolve(strict=True)
        with selected.open("rb") as stream:
            return _identify(selected, stream)
    except (OSError, ValueError):
        return None


def _same_file(expected: FileIdentity, current: FileIdentity, stream: BinaryIO) -> bool:
    if (expected.path, expected.dev, expected.ino, expected.anchor_offset) != (
        current.path, current.dev, current.ino, current.anchor_offset,
    ) or not expected.anchor_offset < expected.size <= current.size:
        return False
    stream.seek(expected.anchor_offset)
    length = min(_ANCHOR_BYTES, expected.size - expected.anchor_offset)
    return hashlib.sha256(stream.read(length)).hexdigest() == expected.content_digest


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(
            item["text"] for item in value
            if isinstance(item, Mapping) and item.get("type") == "text" and isinstance(item.get("text"), str)
        ).strip()
    return ""


def _timestamp(row: Mapping[str, Any]) -> float | None:
    raw = row.get("timestamp")
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except (OverflowError, ValueError):
        return None


def read_material(path: str | Path, start: int = 0, *, scan_until: int | None = None, session_id: str | None = None, not_before: float | None = None, expected: FileIdentity | None = None, **_kwargs: Any) -> dict[str, Any]:
    selected = Path(path).resolve()
    start = max(0, int(start))
    result = {"status": "ok", "start": start, "end": start, "digest": _EMPTY_SHA256,
              "text": "", "records": 0, "partial": False, "more": False, "timestamps_reliable": True}
    consumed = start
    pieces: list[str] = []
    try:
        with selected.open("rb") as stream:
            current = _identify(selected, stream)
            result["identity"] = current.serialize()
            limit = current.size if scan_until is None else min(current.size, int(scan_until))
            if limit < start or (expected is not None and not _same_file(expected, current, stream)):
                return {**result, "status": "replaced"}
            if limit - start > _MAX_SCAN_BYTES:
                return {**result, "status": "oversize"}
            stream.seek(current.anchor_offset)
            header_line = stream.readline(min(_MAX_HEADER_BYTES + 1, max(0, limit - current.anchor_offset)))
            if len(header_line) > _MAX_HEADER_BYTES:
                return {**result, "status": "oversize"}
            if not header_line.endswith(b"\n"):
                return {**result, "partial": True, "more": start < current.size}
            try:
                header = json.loads(header_line.decode("utf-8"))
            except ValueError:
                return {**result, "status": "unknown-format"}
            if not isinstance(header, dict) or header.get("type") != "session" or not header.get("id") or not isinstance(header["id"], str):
                return {**result, "status": "unknown-format"}
            if session_id is not None and session_id != header["id"]:
                return {**result, "status": "wrong-task"}
            consumed = max(start, stream.tell())
            stream.seek(consumed)
            while consumed < limit:
                line = stream.readline(limit - consumed)
                if not line.endswith(b"\n"):
                    result["partial"] = True
                    break
                try:
                    row = json.loads(line.decode("utf-8"))
                except ValueError:
                    return {**result, "status": "invalid-record"}
                consumed += len(line)
                if not isinstance(row, dict) or row.get("type") != "message":
                    continue
                message = row.get("message")
                if not isinstance(message, dict) or message.get("role") not in ("user", "assistant"):
                    continue
                if message.get("synthetic") or message.get("parentIrc"):
                    continue
                text = _text(message.get("content"))
                if not text:
                    continue
                if not_before is not None:
                    timestamp = _timestamp(row)
                    if timestamp is None:
                        return {**result, "status": "invalid-record", "timestamps_reliable": False}
                    if timestamp < not_before:
                        continue
                pieces.append(f"{message['role'].title()}\n{text}")
    except FileNotFoundError:
        return {**result, "status": "missing"}
    except TimeoutError:
        raise
    except OSError:
        return {**result, "status": "unreadable"}
    result["records"] = len(pieces)
    result["end"] = consumed
    result["more"] = consumed < current.size
    result["text"] = "\n\n".join(pieces)
    result["digest"] = hashlib.sha256(result["text"].encode("utf-8")).hexdigest()
    return result


read_increment = read_material
