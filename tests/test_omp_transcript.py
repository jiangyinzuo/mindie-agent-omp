import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.omp_transcript import FileIdentity, identify, read_material


STAMP = "2026-11-28T00:00:01.000Z"
BOUNDARY = 1795824001.0


def _line(record):
    return json.dumps(record, separators=(",", ":")).encode("utf-8") + b"\n"


def _title(name):
    record = {"type": "title", "v": 1, "title": name, "updatedAt": STAMP, "pad": ""}
    record["pad"] = " " * (256 - len(_line(record)))
    return _line(record)


def _header():
    return _line({"type": "session", "version": 3, "id": "session-1", "timestamp": STAMP, "cwd": "/workspace"})


def _message(role, content, timestamp=STAMP, **flags):
    return _line({"type": "message", "timestamp": timestamp, "message": {"role": role, "content": content, **flags}})


class OmpTranscriptTest(unittest.TestCase):
    def setUp(self):
        scratch = self.enterContext(TemporaryDirectory())
        self.path = Path(scratch) / "session.jsonl"

    def test_projects_visible_messages_after_boundary(self):
        self.path.write_bytes(
            _header()
            + _message("user", "before consent", "2026-11-28T00:00:00.000Z")
            + _message("user", "question")
            + _message("user", "synthetic", synthetic=True)
            + _message("assistant", [
                {"type": "thinking", "text": "private reasoning"},
                {"type": "toolCall", "text": "tool arguments"},
                {"type": "text", "text": "answer"},
            ])
            + _message("toolResult", "tool output")
        )
        result = read_material(self.path, session_id="session-1", not_before=BOUNDARY)
        self.assertEqual((result["status"], result["text"], result["records"]), ("ok", "User\nquestion\n\nAssistant\nanswer", 2))
        self.assertEqual(result["end"], self.path.stat().st_size)
        wrong = read_material(self.path, session_id="other", not_before=BOUNDARY)
        self.assertEqual((wrong["status"], wrong["text"], wrong["end"]), ("wrong-task", "", 0))

    def test_resumes_after_title_update_but_rejects_changed_transcript(self):
        self.path.write_bytes(_title("original") + _header() + _message("user", "first"))
        first = read_material(self.path, session_id="session-1")
        expected = FileIdentity.unserialize(first["identity"])
        with self.path.open("r+b") as stream:
            stream.write(_title("updated, longer title"))
            stream.seek(0, 2)
            stream.write(_message("assistant", "new answer"))
        current = identify(self.path)
        self.assertEqual((current.anchor_len, current.anchor_digest), (expected.anchor_len, expected.anchor_digest))
        second = read_material(self.path, first["end"], session_id="session-1", expected=expected)
        self.assertEqual((second["status"], second["text"]), ("ok", "Assistant\nnew answer"))
        with self.path.open("r+b") as stream:
            stream.seek(256 + len(_header()))
            stream.write(_message("user", "other"))
        changed = read_material(self.path, first["end"], session_id="session-1", expected=expected)
        self.assertEqual((changed["status"], changed["text"]), ("replaced", ""))
        self.path.write_bytes(_title("updated") + _header())
        truncated = read_material(self.path, first["end"], session_id="session-1", expected=expected)
        self.assertEqual(truncated["status"], "replaced")

    def test_does_not_consume_unfinished_record(self):
        prefix = _header() + _message("user", "first")
        unfinished = _message("assistant", "not flushed")[:-1]
        self.path.write_bytes(prefix + unfinished)
        result = read_material(self.path, session_id="session-1")
        self.assertEqual((result["partial"], result["end"], result["text"]), (True, len(prefix), "User\nfirst"))
        with self.path.open("ab") as stream:
            stream.write(b"\n")
        next_page = read_material(self.path, result["end"], session_id="session-1",
                                  expected=FileIdentity.unserialize(result["identity"]))
        self.assertEqual(next_page["text"], "Assistant\nnot flushed")
