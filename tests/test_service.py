"""Tests for footprint_core.service."""
from footprint_core import config, service


def _cp1252_default_open(real_open):
    def fake_open(file, mode="r", *args, **kwargs):
        if "b" not in mode:
            kwargs.setdefault("encoding", "cp1252")
        return real_open(file, mode, *args, **kwargs)
    return fake_open


def test_opencode_command_file_is_written_as_utf8(tmp_path, monkeypatch):
    """The command description contains an em dash; opencode reads the file as UTF-8."""
    monkeypatch.setattr(config, "OPENCODE", str(tmp_path))
    monkeypatch.setattr(service, "open", _cp1252_default_open(open), raising=False)

    service._opencode()

    cmd = (tmp_path / "commands" / "footprint.md").read_text(encoding="utf-8")
    assert "local model trained on your Claude sessions" in cmd
    assert "—" in cmd


def _provider(path):
    import json
    return json.loads(path.read_text(encoding="utf-8"))["provider"]["footprint"]["options"]["baseURL"]


def test_opencode_adds_provider_to_existing_jsonc(tmp_path, monkeypatch):
    """A user with only opencode.jsonc gets the provider there, not in a second opencode.json."""
    monkeypatch.setattr(config, "OPENCODE", str(tmp_path))
    (tmp_path / "opencode.jsonc").write_text('{"$schema": "https://opencode.ai/config.json", "theme": "x"}')

    service._opencode()

    assert not (tmp_path / "opencode.json").exists()
    assert _provider(tmp_path / "opencode.jsonc").endswith("/v1")
    assert '"theme": "x"' in (tmp_path / "opencode.jsonc").read_text()


def test_opencode_never_rewrites_jsonc_with_comments(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "OPENCODE", str(tmp_path))
    original = '{\n  // my settings\n  "theme": "x"\n}\n'
    (tmp_path / "opencode.jsonc").write_text(original)

    service._opencode()

    assert (tmp_path / "opencode.jsonc").read_text() == original
    assert '"footprint"' in capsys.readouterr().out
    assert (tmp_path / "commands" / "footprint.md").exists()
