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


def test_rejected_marks_corrected_and_interrupted_tasks():
    u = lambda t: {"role": "user", "content": t}
    a = lambda t: {"role": "assistant", "content": t}
    msgs = [u("add login"), a("used email auth"),            # task 1: user pushes back next -> rejected
            u("no, use github oauth"), a('<tool name="Edit">{}</tool>'),
            u("<tool_result>ok</tool_result>"), a("done"),   # task 2: user moves on -> accepted
            u("now add tests"), a("<tool>"),                 # task 3: interrupted -> rejected
            u("<tool_result>x</tool_result>\n[Request interrupted by user]")]
    assert transcripts.rejected(msgs) == [True, True, False, False, False, False, True, True, True]


def test_parse_native_maps_claude_tools_to_opencode(tmp_path):
    rows = [{"type": "user", "message": {"role": "user", "content": "rename the button<system-reminder>x</system-reminder>"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "On it."}]}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "e1", "name": "Edit",
                 "input": {"file_path": "/a.tsx", "old_string": "Go", "new_string": "Start"}}]}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "TodoWrite", "input": {"todos": []}}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "e1", "content": "edited"},
                {"type": "tool_result", "tool_use_id": "t1", "content": "todos saved"}]}},
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Renamed."}]}}]
    p = tmp_path / "s.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    msgs = transcripts.parse_native(str(p))
    assert msgs[0] == {"role": "user", "content": "rename the button"}
    assert msgs[1]["content"] == "On it." and msgs[1]["tool_calls"] == [{"id": "e1", "type": "function", "function": {
        "name": "edit", "arguments": {"filePath": "/a.tsx", "oldString": "Go", "newString": "Start"}}}]
    assert msgs[2] == {"role": "tool", "tool_call_id": "e1", "content": "edited"}  # TodoWrite call + result dropped
    assert msgs[3] == {"role": "assistant", "content": "Renamed."} and len(msgs) == 4
