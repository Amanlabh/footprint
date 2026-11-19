"""Tests for footprint_core.compress backend choice (llmlingua or ctxprune) and its cache."""
import sys
import types

from footprint_core import compress, config

LONG = "x " * 400  # above MIN_CHARS


def _rows():
    return [{"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "q"},
                          {"role": "tool", "content": LONG}, {"role": "assistant", "content": "a"}]}]


def _fake(monkeypatch, module, calls):
    class PromptCompressor:
        def __init__(self, **kw):
            calls.append((module, kw))

        def compress_prompt(self, text, **kw):
            calls.append((module, kw))
            return {"compressed_prompt": f"[{module}]"}

    mod = types.ModuleType(module)
    mod.PromptCompressor = PromptCompressor
    monkeypatch.setitem(sys.modules, module, mod)
    if module == "ctxprune.compat":
        monkeypatch.setitem(sys.modules, "ctxprune", types.ModuleType("ctxprune"))


def test_each_backend_uses_its_own_import_and_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA", str(tmp_path))
    calls = []
    _fake(monkeypatch, "ctxprune.compat", calls)
    _fake(monkeypatch, "llmlingua", calls)
    out, stats = compress.compress(_rows(), say=lambda *_: None, backend="ctxprune")
    assert out[0]["messages"][2]["content"] == "[ctxprune.compat]" and stats["outputs"] == 1
    # switching backend must not reuse the other backend's cached text
    out, _ = compress.compress(_rows(), say=lambda *_: None, backend="llmlingua")
    assert out[0]["messages"][2]["content"] == "[llmlingua]"
    kw = [c[1] for c in calls if "rate" in c[1]]
    assert kw[0]["protect"] is True and "protect" not in kw[1]  # protect=True only for the ctxprune backend


def test_missing_package_skips_compression(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA", str(tmp_path))
    monkeypatch.setitem(sys.modules, "ctxprune", None)  # makes `import ctxprune.compat` raise ImportError
    said = []
    rows = _rows()
    out, stats = compress.compress(rows, say=said.append, backend="ctxprune")
    assert out is rows and stats is None and "pip install ctxprune" in said[0]
