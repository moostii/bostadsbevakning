from pathlib import Path

from bevakning.__main__ import main

ROOT = Path(__file__).resolve().parent.parent


def test_real_run_without_topic_exits_2(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    state = tmp_path / "seen.json"
    code = main(["--config", str(ROOT / "config.yaml"), "--state", str(state)])
    assert code == 2
    assert "NTFY_TOPIC" in capsys.readouterr().err
    assert not state.exists()
