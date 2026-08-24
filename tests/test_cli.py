import json
from pathlib import Path

import pytest

from todo_audit.cli import main


def test_scan_outputs_sorted_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "a.py").write_text("# TODO: plain one\n# !TODO: urgent one\n", encoding="utf-8")

    exit_code = main(["scan", str(tmp_path)])
    assert exit_code == 0, "a scan that finds TODOs must still exit 0"

    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 2, "both markers in the file must reach the payload"
    assert [t["type"] for t in payload["todos"]] == ["urgent", "plain"], (
        "the CLI must emit todos already sorted: urgent ahead of plain"
    )
    assert payload["todos"][0]["color"] == "red", "an urgent TODO must carry the red presentation color"


def test_scan_empty_tree(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["scan", str(tmp_path)])
    assert exit_code == 0, "finding nothing is a success, not an error"
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 0, "an empty tree must report a zero count"
    assert payload["todos"] == [], "an empty tree must emit an empty list, not a null"


def test_missing_subcommand_errors() -> None:
    with pytest.raises(SystemExit):
        main([])


def test_payload_carries_a_summary_and_the_vocabulary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "a.py").write_text("# FIXME: broken\n# ?TODO: unclear\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("# TODO: routine\n", encoding="utf-8")

    assert main(["scan", str(tmp_path)]) == 0, "the scan must succeed"
    payload = json.loads(capsys.readouterr().out)

    summary = payload["summary"]
    assert summary["by_type"] == {"urgent": 1, "question": 1, "plain": 1}, (
        "the summary must let the model prioritize without walking the whole array"
    )
    assert summary["by_marker"] == {"FIXME": 1, "TODO": 2}, "the summary must break down by keyword too"
    assert summary["files"] == 2, "the summary must report how many files are involved"

    vocabulary = payload["vocabulary"]
    assert vocabulary["difficulty"]["5"] == "solution requiring complete redesign", (
        "the difficulty labels must travel in the payload so the prose copies cannot drift from the code"
    )
    assert vocabulary["fix_kinds"] == ["system", "temporary"], "the fix-kind vocabulary must travel with the payload"
    assert vocabulary["severity_order"] == ["urgent", "question", "plain"], "the severity order must be stated once"


def test_missing_root_is_reported_not_silently_empty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["scan", str(tmp_path / "typo")])
    assert exit_code == 2, "a mistyped path must fail, not report a clean bill of health"
    captured = capsys.readouterr()
    assert "no such file or directory" in captured.err, "the error must name the problem"
    assert captured.out == "", "a failed scan must emit no JSON payload"


def test_dependency_root_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    site = tmp_path / ".venv" / "lib" / "python3.12" / "site-packages"
    site.mkdir(parents=True)
    (site / "dep.py").write_text("# TODO: third-party\n", encoding="utf-8")

    exit_code = main(["scan", str(site)])
    assert exit_code == 2, "refusing to audit third-party code must be a distinct failure, not a clean empty scan"
    captured = capsys.readouterr()
    assert "third-party" in captured.err, "the refusal must say why, so the user knows to repoint at their project"
    assert captured.out == "", "a refused scan must emit no JSON payload at all"


def test_warns_when_gitignore_cannot_be_enforced(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None)
    (tmp_path / ".gitignore").write_text("secret/\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("# TODO: one\n", encoding="utf-8")

    assert main(["scan", str(tmp_path)]) == 0, "a missing optional dependency must not fail the scan"
    captured = capsys.readouterr()
    assert "pathspec" in captured.err, (
        "unenforced .gitignore rules must be announced on stderr, naming the package that would fix it"
    )
    assert json.loads(captured.out)["count"] == 1, "the warning must go to stderr and leave stdout valid JSON"


def test_no_warning_without_a_gitignore(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None)
    (tmp_path / "a.py").write_text("# TODO: one\n", encoding="utf-8")

    assert main(["scan", str(tmp_path)]) == 0, "scanning a tree without a .gitignore must succeed"
    assert capsys.readouterr().err == "", "with no .gitignore present there is nothing to warn about"


def test_no_warning_when_pathspec_is_present(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pytest.importorskip("pathspec")
    (tmp_path / ".gitignore").write_text("secret/\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("# TODO: one\n", encoding="utf-8")

    assert main(["scan", str(tmp_path)]) == 0, "a scan with ignore rules applied must exit 0"
    assert capsys.readouterr().err == "", "rules that are actually enforced must not produce a warning"
