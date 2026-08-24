"""Traversal honors the denylist, nested .gitignore files, and the size cap."""

import importlib.util
import sys
from pathlib import Path
from typing import Any, List, Set

import pytest

from todo_audit import scan_file, scan_path
from todo_audit.ignore import GitignoreIndex, _ancestor_dirs, _verdict
from todo_audit.scanner import MAX_FILE_BYTES, is_denied_dir, is_dependency_path

_HAS_PATHSPEC = importlib.util.find_spec("pathspec") is not None
_needs_pathspec = pytest.mark.skipif(not _HAS_PATHSPEC, reason="pathspec not installed")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _files(root: Path) -> Set[str]:
    return {t.file.replace("\\", "/") for t in scan_path(str(root))}


# --- built-in denylist -----------------------------------------------------


def test_denylisted_dir_skipped(tmp_path: Path) -> None:
    _write(tmp_path / "keep.py", "# TODO: keep me\n")
    _write(tmp_path / "node_modules" / "dep.py", "# TODO: ignore me\n")
    files = _files(tmp_path)
    assert "keep.py" in files, "pruning node_modules must not disturb ordinary files"
    assert not any("node_modules" in f for f in files), (
        "node_modules is denylisted unconditionally, with or without a .gitignore"
    )


def test_egg_info_dir_skipped_by_suffix(tmp_path: Path) -> None:
    _write(tmp_path / "keep.py", "# TODO: keep me\n")
    _write(tmp_path / "mypkg.egg-info" / "meta.py", "# TODO: build artifact\n")
    assert _files(tmp_path) == {"keep.py"}, (
        "real directories are named `<pkg>.egg-info`, so an exact-match denylist entry never fires; "
        "the suffix rule is what prunes them"
    )


@pytest.mark.parametrize(
    ("name", "denied"),
    [("node_modules", True), ("anything.egg-info", True), ("src", False), ("egg-info", False)],
)
def test_is_denied_dir_rules(name: str, denied: bool) -> None:
    verb = "must be pruned" if denied else "must be traversed"
    assert is_denied_dir(name) is denied, f"a directory named {name!r} {verb}"


# --- third-party code is never audited -------------------------------------


@pytest.mark.parametrize("venv_name", ["myenv", "env", "whatever", ".venv"])
def test_virtualenv_is_pruned_whatever_it_is_named(tmp_path: Path, venv_name: str) -> None:
    venv = tmp_path / venv_name
    (venv / "pyvenv.cfg").parent.mkdir(parents=True, exist_ok=True)
    (venv / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    _write(venv / "lib" / "python3.12" / "site-packages" / "dep.py", "# TODO: third-party\n")
    _write(tmp_path / "app.py", "# TODO: my own code\n")
    assert _files(tmp_path) == {"app.py"}, (
        f"a virtual environment named {venv_name!r} must be pruned; pyvenv.cfg identifies it regardless of name"
    )


@pytest.mark.parametrize(
    "vendor_dir",
    ["node_modules", "vendor", "bower_components", "Pods", "Carthage", "third_party", ".yarn", "site-packages"],
)
def test_vendor_directories_are_pruned(tmp_path: Path, vendor_dir: str) -> None:
    _write(tmp_path / vendor_dir / "pkg" / "code.js", "// !TODO: third-party\n")
    _write(tmp_path / "app.py", "# TODO: my own code\n")
    assert _files(tmp_path) == {"app.py"}, f"{vendor_dir}/ holds installed code, not code the user wrote"


@pytest.mark.parametrize("generated_dir", ["dist", "build", "target", ".next", "coverage", ".terraform"])
def test_generated_directories_are_pruned(tmp_path: Path, generated_dir: str) -> None:
    _write(tmp_path / generated_dir / "out.js", "// TODO: generated output\n")
    _write(tmp_path / "app.py", "# TODO: my own code\n")
    assert _files(tmp_path) == {"app.py"}, f"{generated_dir}/ holds build output, which nobody edits by hand"


@pytest.mark.parametrize("name", ["app.min.js", "styles.min.css", "vendor.bundle.js", "schema_pb2.py", "api.pb.go"])
def test_generated_files_are_skipped(tmp_path: Path, name: str) -> None:
    _write(tmp_path / name, "// TODO: machine generated\n")
    _write(tmp_path / "app.py", "# TODO: my own code\n")
    assert _files(tmp_path) == {"app.py"}, f"{name} is machine-generated, so a TODO inside it is not actionable"


def test_scan_refuses_a_dependency_root(tmp_path: Path) -> None:
    site = tmp_path / ".venv" / "lib" / "python3.12" / "site-packages"
    _write(site / "dep.py", "# TODO: third-party\n")
    assert scan_path(str(site)) == [], (
        "naming a dependency directory as the scan root must not smuggle third-party code into an audit"
    )


def test_a_project_directory_named_build_is_still_scannable(tmp_path: Path) -> None:
    # `build` is pruned during traversal, but as an explicit root it is the
    # user's own tree and must not be refused
    _write(tmp_path / "build" / "app.py", "# TODO: my own code\n")
    assert _files(tmp_path / "build") == {"app.py"}, (
        "generated-output names are pruned when nested, not when the user points at one directly"
    )


def test_is_dependency_path_leaves_ordinary_projects_alone(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "app.py", "# TODO: one\n")
    assert is_dependency_path(tmp_path / "src") is False, "an ordinary project directory must never be refused"


# --- .gitignore, at every level -------------------------------------------


@_needs_pathspec
def test_root_gitignore_skipped(tmp_path: Path) -> None:
    _write(tmp_path / ".gitignore", "secret/\n")
    _write(tmp_path / "keep.py", "# TODO: keep me\n")
    _write(tmp_path / "secret" / "hidden.py", "# TODO: hidden\n")
    assert _files(tmp_path) == {"keep.py"}, "a rule in the root .gitignore must prune the directory it names"


@_needs_pathspec
def test_nested_gitignore_is_honored(tmp_path: Path) -> None:
    _write(tmp_path / "sub" / ".gitignore", "skip/\n")
    _write(tmp_path / "sub" / "keep.py", "# TODO: keep me\n")
    _write(tmp_path / "sub" / "skip" / "hidden.py", "# TODO: hidden\n")
    assert _files(tmp_path) == {"sub/keep.py"}, (
        "a .gitignore below the scan root must apply to its own subtree, not only the root file"
    )


@_needs_pathspec
def test_nested_gitignore_does_not_leak_upward(tmp_path: Path) -> None:
    _write(tmp_path / "sub" / ".gitignore", "hidden.py\n")
    _write(tmp_path / "sub" / "hidden.py", "# TODO: ignored here\n")
    _write(tmp_path / "other" / "hidden.py", "# TODO: kept there\n")
    assert _files(tmp_path) == {"other/hidden.py"}, (
        "a rule declared in sub/ governs sub/ only; a sibling directory must be unaffected"
    )


@_needs_pathspec
def test_negation_reincludes_a_file(tmp_path: Path) -> None:
    _write(tmp_path / ".gitignore", "*.py\n!keep.py\n")
    _write(tmp_path / "keep.py", "# TODO: keep me\n")
    _write(tmp_path / "drop.py", "# TODO: drop me\n")
    assert _files(tmp_path) == {"keep.py"}, "a later `!` pattern must re-include what an earlier pattern excluded"


@_needs_pathspec
def test_closest_gitignore_wins_over_the_root(tmp_path: Path) -> None:
    _write(tmp_path / ".gitignore", "*.py\n")
    _write(tmp_path / "top.py", "# TODO: excluded at root\n")
    _write(tmp_path / "sub" / ".gitignore", "!*.py\n")
    _write(tmp_path / "sub" / "inner.py", "# TODO: re-included\n")
    assert _files(tmp_path) == {"sub/inner.py"}, (
        "git precedence: the deepest .gitignore with an opinion decides, so sub/ re-includes what the root excluded"
    )


@_needs_pathspec
def test_unreadable_gitignore_is_ignored(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_bytes(b"\xff\xfe\x00bad")
    _write(tmp_path / "keep.py", "# TODO: keep me\n")
    assert _files(tmp_path) == {"keep.py"}, "a .gitignore that cannot be decoded must be skipped, not crash the scan"


def test_ancestor_dirs_deepest_first() -> None:
    assert _ancestor_dirs("a/b/c.py") == ["a/b", "a", ""], (
        "candidate directories must be ordered deepest first so the closest .gitignore is consulted first"
    )
    assert _ancestor_dirs("top.py") == [""], "a root-level path has exactly one candidate directory: the root itself"


def test_empty_index_ignores_nothing() -> None:
    assert GitignoreIndex().is_ignored("anything.py") is False, (
        "an index holding no rules must ignore nothing rather than guess"
    )


def test_load_dir_without_a_gitignore_is_a_noop(tmp_path: Path) -> None:
    index = GitignoreIndex()
    index.load_dir("", tmp_path)
    assert index.is_ignored("a.py") is False, "loading a directory that has no .gitignore must register no rules"


class _LegacySpec:
    """Stand-in for a pathspec release predating ``check_file``."""

    def __init__(self, hits: List[str]) -> None:
        self._hits = hits

    def match_file(self, rel: str) -> bool:
        return rel in self._hits


def test_verdict_falls_back_to_match_file() -> None:
    spec: Any = _LegacySpec(["a.py"])
    assert _verdict(spec, "a.py") is True, "without check_file, a match must still be reported as ignored"
    assert _verdict(spec, "b.py") is None, (
        "an old spec cannot distinguish 'no match' from 'negated', so it must report no opinion "
        "and let a shallower .gitignore decide"
    )


def test_without_pathspec_nothing_is_gitignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # `sys.modules[name] = None` makes `import name` raise ImportError
    monkeypatch.setitem(sys.modules, "pathspec", None)
    _write(tmp_path / ".gitignore", "secret/\n")
    _write(tmp_path / "secret" / "hidden.py", "# TODO: no pathspec, no filtering\n")
    assert _files(tmp_path) == {"secret/hidden.py"}, (
        "without the optional pathspec package the scan must degrade to the denylist, not fail"
    )


@_needs_pathspec
@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_legacy_pathspec_factory_name_is_tolerated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pathspec = pytest.importorskip("pathspec")
    original = pathspec.PathSpec.from_lines

    def only_gitwildmatch(pattern_factory: Any, lines: Any, **kwargs: Any) -> Any:
        if pattern_factory == "gitignore":
            raise KeyError(pattern_factory)
        return original(pattern_factory, lines, **kwargs)

    monkeypatch.setattr(pathspec.PathSpec, "from_lines", staticmethod(only_gitwildmatch))
    _write(tmp_path / ".gitignore", "secret/\n")
    _write(tmp_path / "keep.py", "# TODO: keep me\n")
    _write(tmp_path / "secret" / "hidden.py", "# TODO: hidden\n")
    assert _files(tmp_path) == {"keep.py"}, (
        "releases predating the 'gitignore' factory alias must fall back to 'gitwildmatch' instead of crashing"
    )


def test_verdict_uses_check_file_when_available() -> None:
    pathspec = pytest.importorskip("pathspec")
    spec = pathspec.PathSpec.from_lines("gitignore", ["*.py", "!keep.py"])
    assert _verdict(spec, "drop.py") is True, "a matched pattern must report the file as ignored"
    assert _verdict(spec, "keep.py") is False, "a negated match must report re-inclusion, distinct from no opinion"
    assert _verdict(spec, "notes.txt") is None, (
        "an unmatched path must report no opinion so a shallower .gitignore still gets a say"
    )


# --- size cap -------------------------------------------------------------


def test_oversized_file_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("todo_audit.scanner.MAX_FILE_BYTES", 32)
    _write(tmp_path / "small.py", "# TODO: small\n")
    _write(tmp_path / "big.py", "# TODO: big\n" + "# padding padding padding\n" * 4)
    assert _files(tmp_path) == {"small.py"}, "a file past the size cap must be skipped before it is read into memory"


def test_default_size_cap_is_five_megabytes() -> None:
    assert MAX_FILE_BYTES == 5 * 1024 * 1024, (
        "the documented cap is 5 MB; changing it means updating README.md and SKILL.md too"
    )


def test_latin1_file_still_yields_its_markers(tmp_path: Path) -> None:
    # one stray byte must not silently discard every TODO in the file
    (tmp_path / "legacy.py").write_bytes("# TODO: keep me\nname = 'caf\xe9'\n".encode("latin-1"))
    assert _files(tmp_path) == {"legacy.py"}, (
        "undecodable bytes are replaced, not fatal: dropping the whole file loses real work silently"
    )


def test_binary_file_wearing_a_source_extension_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "blob.py").write_bytes(b"\x00\x01\x02 TODO: not really source")
    assert scan_path(str(tmp_path)) == [], "a NUL byte means binary data, which has no comments to find"


def test_scan_file_on_a_directory_is_tolerated(tmp_path: Path) -> None:
    # a directory whose name ends in .py passes the extension check, then fails
    # to read; that must be shrugged off rather than raised
    weird = tmp_path / "looks_like_source.py"
    weird.mkdir()
    assert scan_file(str(weird)) == [], "an unreadable path must yield no markers instead of propagating an OSError"


def test_missing_root_raises_rather_than_reporting_a_clean_scan(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        scan_path(str(tmp_path / "no-such-directory"))


def test_a_single_file_can_be_scanned_directly(tmp_path: Path) -> None:
    target = tmp_path / "one.py"
    _write(target, "# !TODO: just this file\n")
    _write(tmp_path / "other.py", "# TODO: not asked for\n")
    todos = scan_path(str(target))
    assert [t.file for t in todos] == ["one.py"], (
        "pointing at a file must scan that file, not silently report nothing because it is not a directory"
    )


def test_a_file_inside_a_dependency_tree_is_still_refused(tmp_path: Path) -> None:
    target = tmp_path / "node_modules" / "pkg" / "index.js"
    _write(target, "// TODO: third-party\n")
    assert scan_path(str(target)) == [], "naming a single vendored file must not bypass the third-party rule"


def test_directory_named_like_a_source_file_is_not_scanned(tmp_path: Path) -> None:
    (tmp_path / "weird.py").mkdir()
    _write(tmp_path / "weird.py" / "inner.py", "# TODO: nested\n")
    assert _files(tmp_path) == {"weird.py/inner.py"}, (
        "a directory whose name ends in .py must be descended into, not read as a source file"
    )
