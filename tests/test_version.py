"""The package version has exactly one source of truth."""

import json
import subprocess
import sys
from pathlib import Path

import todo_audit

REPO = Path(__file__).parent.parent
PACKAGE_JSON = REPO / "package.json"
PLUGIN_JSON = REPO / ".claude-plugin" / "plugin.json"
SYNC_SCRIPT = REPO / "tools" / "sync_version.py"
_SYNC_HINT = "run `uv run poe sync-version` to propagate it"


def _json_version(path: Path) -> str:
    return str(json.loads(path.read_text(encoding="utf-8"))["version"])


def test_manifests_match_the_package_version() -> None:
    assert _json_version(PACKAGE_JSON) == todo_audit.__version__, f"package.json is out of sync; {_SYNC_HINT}"
    assert _json_version(PLUGIN_JSON) == todo_audit.__version__, f"plugin.json is out of sync; {_SYNC_HINT}"


def test_pyproject_takes_its_version_dynamically() -> None:
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert 'dynamic = ["version"]' in pyproject, (
        "a literal version in pyproject.toml would become a second source of truth"
    )
    assert 'version = { attr = "todo_audit.__version__" }' in pyproject, (
        "setuptools must read the version from todo_audit.__version__"
    )


def test_sync_version_check_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"the version sync check failed; {_SYNC_HINT}\n{result.stderr}"


def test_author_is_consistent_across_manifests() -> None:
    author = "Ákos Jakub (arathus)"
    assert json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))["author"] == author, (
        f"package.json must credit the author as {author!r}"
    )
    # plugin.json and marketplace.json require an object, not a bare string
    assert json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))["author"]["name"] == author, (
        f"plugin.json must credit the author as {author!r}"
    )
    marketplace = REPO / ".claude-plugin" / "marketplace.json"
    assert json.loads(marketplace.read_text(encoding="utf-8"))["owner"]["name"] == author, (
        f"marketplace.json must credit the owner as {author!r}"
    )
    assert f'name = "{author}"' in (REPO / "pyproject.toml").read_text(encoding="utf-8"), (
        f"pyproject.toml must credit the author as {author!r}"
    )
