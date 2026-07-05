import json
from pathlib import Path

import pytest

from todo_audit.cli import main


def test_scan_outputs_sorted_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "a.py").write_text("# TODO: plain one\n# !TODO: urgent one\n", encoding="utf-8")

    exit_code = main(["scan", str(tmp_path)])
    assert exit_code == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 2
    # urgent sorts before plain
    assert [t["type"] for t in payload["todos"]] == ["urgent", "plain"]
    assert payload["todos"][0]["color"] == "red"


def test_scan_empty_tree(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["scan", str(tmp_path)])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 0
    assert payload["todos"] == []


def test_missing_subcommand_errors() -> None:
    with pytest.raises(SystemExit):
        main([])
