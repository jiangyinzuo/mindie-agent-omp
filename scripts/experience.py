"""Run MindIE's pinned scanner with the OMP runtime interpreter."""

import json
from pathlib import Path
import secrets
import signal
import sys
import threading

from mindie_knowledge.loop.transcript_redaction import install_scanner, redact


def main():
    operation, *args = sys.argv[1:]
    if operation == "install-scanner":
        print(install_scanner(cache=Path(args[0])))
        return
    if operation != "redact":
        raise ValueError("unknown local experience operation")

    scanner, workspace, limit = args
    limit = int(limit)
    raw = sys.stdin.buffer.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("transcript exceeds local capture limit")

    cancelled = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: cancelled.set())
    body, _ = redact(
        raw.decode("utf-8"), executable=scanner, key=secrets.token_bytes(32),
        private_paths=(workspace, str(Path.home())), cancel=cancelled, timeout=8.0,
    )
    print(json.dumps(body, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"MindIE {sys.argv[1]} failed ({type(exc).__name__}).", file=sys.stderr)
        sys.exit(1)
