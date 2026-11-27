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

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_MAX_SCAN_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class FileIdentity:
    path: str
    dev: int
    ino: int
    size: int
    mtime_ns: int
    anchor_len: int = 0
    anchor_digest: str = ""

    def serialize(self) -> str:
        return json.dumps(self.__dict__, sort_keys=True, separators=(",", ":"))

    @classmethod
    def unserialize(cls, payload: Mapping[str, Any] | str, path: str | Path | None = None) -> "FileIdentity | None":
        try:
            data = json.loads(payload) if isinstance(payload, str) else dict(payload)
            if not isinstance(data, dict):
                return None
            raw_path = path or data.get("path")
            values = {key: data[key] for key in ("dev", "ino", "size", "mtime_ns", "anchor_len", "anchor_digest")}
            if not isinstance(raw_path, (str, Path)):
                return None
            return cls(str(Path(raw_path).resolve()), **values)
        except (KeyError, TypeError, ValueError, OSError):
            return None


def identify(path: str | Path) -> FileIdentity | None:
    try:
        selected = Path(path).resolve(strict=True)
        stat = selected.stat()
        with selected.open("rb") as stream:
            anchor = stream.read(512)
        return FileIdentity(str(selected), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, len(anchor), hashlib.sha256(anchor).hexdigest())
    except (OSError, ValueError):
        return None


def _same_file(expected: FileIdentity, current: FileIdentity) -> bool:
    return expected.path == current.path and expected.dev == current.dev and expected.ino == current.ino and (
        expected.anchor_len == 0 or expected.anchor_len == current.anchor_len and expected.anchor_digest == current.anchor_digest
    )


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(_text(item.get("text")) for item in value if isinstance(item, Mapping) and item.get("text")).strip()
    if isinstance(value, Mapping):
        return _text(value.get("text") or value.get("content"))
    return ""


def _timestamp(row: Mapping[str, Any]) -> float | None:
    raw = row.get("timestamp") or row.get("time") or row.get("created_at")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw) / 1000.0 if raw > 10_000_000_000 else float(raw)
    return None


def read_material(path: str | Path, start: int = 0, *, scan_until: int | None = None, session_id: str | None = None, not_before: float | None = None, expected: FileIdentity | None = None, **_kwargs: Any) -> dict[str, Any]:
    selected = Path(path).resolve()
    current = identify(selected)
    result = {"status": "ok", "start": max(0, int(start)), "end": max(0, int(start)), "digest": _EMPTY_SHA256, "text": "", "records": 0, "partial": False, "more": False, "timestamps_reliable": True}
    if current is None:
        result["status"] = "missing"
        return result
    if expected is not None and not _same_file(expected, current):
        result["status"] = "replaced"
        result["identity"] = current.serialize()
        return result
    limit = current.size if scan_until is None else min(current.size, int(scan_until))
    if limit < result["start"] or limit - result["start"] > _MAX_SCAN_BYTES:
        result["status"] = "replaced"
        result["identity"] = current.serialize()
        return result
    try:
        with selected.open("rb") as stream:
            stream.seek(result["start"])
            raw = stream.read(limit - result["start"])
    except OSError:
        result["status"] = "unreadable"
        result["identity"] = current.serialize()
        return result
    consumed = result["start"]
    pieces: list[str] = []
    for line in raw.splitlines(keepends=True):
        consumed += len(line)
        try:
            row = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            result["partial"] = True
            consumed -= len(line)
            break
        if not isinstance(row, Mapping) or session_id and row.get("session_id") != session_id:
            continue
        if not_before is not None and (_timestamp(row) is None or _timestamp(row) < float(not_before)):
            continue
        role = str(row.get("role") or row.get("type") or "").lower()
        text = _text(row.get("content") or row.get("text") or row.get("message"))
        if role in {"user", "assistant"} and text:
            pieces.append(f"{role.title()}\n{text}")
            result["records"] += 1
    result["end"] = consumed
    result["more"] = consumed < current.size
    result["text"] = "\n\n".join(pieces)
    result["digest"] = hashlib.sha256(result["text"].encode("utf-8")).hexdigest()
    result["identity"] = current.serialize()
    return result


read_increment = read_material
