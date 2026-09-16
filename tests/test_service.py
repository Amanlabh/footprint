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

    cmd = (tmp_path / "command" / "footprint.md").read_text(encoding="utf-8")
    assert "local model trained on your Claude sessions" in cmd
    assert "—" in cmd
