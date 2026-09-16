"""Tests for footprint_core.transcripts."""
import json

from footprint_core import transcripts

NON_ASCII = "héllo → “quotes” … 日本語 \U0001F680"


def _write_transcript(path, text):
    rec = {"type": "user", "message": {"role": "user", "content": text}}
    path.write_text(json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(path)


def test_parse_session_preserves_non_ascii_text(tmp_path):
    path = _write_transcript(tmp_path / "session.jsonl", NON_ASCII)

    msgs = transcripts.parse_session(path)

    assert msgs == [{"role": "user", "content": NON_ASCII}]


def test_parse_session_does_not_depend_on_locale_encoding(tmp_path, monkeypatch):
    """Simulate a Windows cp1252 locale so the check is meaningful on every platform."""
    path = _write_transcript(tmp_path / "session.jsonl", NON_ASCII)
    real_open = open

    def cp1252_default_open(file, mode="r", *args, **kwargs):
        if "b" not in mode:
            kwargs.setdefault("encoding", "cp1252")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(transcripts, "open", cp1252_default_open, raising=False)

    msgs = transcripts.parse_session(path)

    assert msgs == [{"role": "user", "content": NON_ASCII}]
