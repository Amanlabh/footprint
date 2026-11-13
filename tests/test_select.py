"""Tests for footprint_core.select (lesson picking) and the collect-side quality filter."""
import json

from footprint_core import select, transcripts


def _lesson(ask, text="", **call):
    answer = {"role": "assistant", "content": text}
    if call:
        answer["tool_calls"] = [{"id": "x", "function": {"name": "bash", "arguments": call}}]
    return {"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": ask}, answer]}


TOGGLE = _lesson("add a dark mode toggle to the settings page", "Added the toggle in settings.tsx and wired the theme context.")
BUILD = _lesson("why is the build failing on ci", "The lockfile is out of date, so the install step fails.")
TESTS = [_lesson("run the tests", command=f"npm test -- module{chr(97 + i)} --watch") for i in range(8)]


def test_near_copies_differing_only_in_numbers_are_dropped():
    a, b = _lesson("run the tests", command="npm test -- auth 12"), _lesson("run the tests", command="npm test -- auth 47")
    kept, dropped = select.dedupe([a, b, TOGGLE])
    assert kept == [a, TOGGLE] and dropped == 1


def test_spread_keeps_the_unlike_lessons():
    got = select.pick(TESTS + [TOGGLE, BUILD], 3)
    assert TOGGLE in got and BUILD in got


def test_surprise_puts_what_the_model_gets_wrong_first():
    rows = TESTS + [TOGGLE, BUILD]
    scores = {select.lesson_id(e): 0.1 for e in rows}
    scores[select.lesson_id(TESTS[3])] = 5.0
    assert select.pick(rows, 1, scores) == [TESTS[3]]


def test_select_never_exceeds_budget_and_reports():
    out, rep = select.select([_lesson("x")] + TESTS + [TOGGLE, BUILD], 4)
    assert len(out) == 4 and rep["low_quality"] == 1 and rep["start"] == 11 and "picked" in select.describe(rep)


def test_parse_native_reports_errored_tool_calls(tmp_path):
    rows = [{"type": "user", "message": {"role": "user", "content": "fix it"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "e1", "name": "Edit", "input": {"file_path": "/a", "old_string": "x", "new_string": "y"}}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "e1", "is_error": True, "content": "String to replace not found"}]}}]
    p = tmp_path / "s.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    errs = set()
    transcripts.parse_native(str(p), errs)
    assert errs == {"e1"}
