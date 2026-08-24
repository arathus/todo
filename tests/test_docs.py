"""Invariants of the skill's own packaging and instructions.

These pin the things that silently stop working: where commands live (which
decides whether they register at all), how the scanner is invoked, and the
safety gates the destructive command is supposed to have.
"""

import json
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
SKILL = REPO / "skills" / "todo-audit-skill" / "SKILL.md"
COMMANDS = REPO / "commands"
PLUGIN_JSON = REPO / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = REPO / ".claude-plugin" / "marketplace.json"
_SKILL_DIR_HINT = "skills/todo-audit-skill}/src"


# --- command layout decides whether the commands exist at all --------------


def test_commands_are_flat_markdown_files() -> None:
    # a plugin named `todo` with commands/audit.md yields /todo:audit; nesting
    # them under commands/todo/ would yield /todo:todo:audit instead
    assert {p.name for p in COMMANDS.glob("*.md")} == {"audit.md", "fix.md", "analyze.md"}, (
        "the three commands must sit directly in commands/ for plugin namespacing to produce /todo:<name>"
    )
    assert not [p for p in COMMANDS.iterdir() if p.is_dir()], (
        "a subdirectory under commands/ adds another namespace segment to every command inside it"
    )


def test_plugin_manifest_is_named_for_the_command_namespace() -> None:
    manifest = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
    assert manifest["name"] == "todo", (
        "plugin commands are namespaced by plugin name, so the plugin must be `todo` to yield /todo:audit"
    )
    assert isinstance(manifest["author"], dict), (
        "plugin.json requires author to be an object with name/email/url, not a plain string"
    )


def test_marketplace_manifest_exists_and_lists_the_plugin() -> None:
    assert MARKETPLACE_JSON.is_file(), (
        "`/plugin marketplace add <owner>/<repo>` reads .claude-plugin/marketplace.json; "
        "without it the documented install cannot even begin"
    )
    catalog = json.loads(MARKETPLACE_JSON.read_text(encoding="utf-8"))
    assert isinstance(catalog.get("owner"), dict), "the marketplace schema requires an owner object"
    names = [p["name"] for p in catalog["plugins"]]
    assert "todo" in names, f"the marketplace must list the plugin it ships; found {names}"


# --- how the scanner is invoked -------------------------------------------


@pytest.mark.parametrize("doc", [SKILL, COMMANDS / "audit.md"])
def test_scan_command_falls_back_to_the_skill_directory(doc: Path) -> None:
    text = doc.read_text(encoding="utf-8")
    assert "todo-audit scan ." in text, f"{doc.name} must show the console-script invocation first"
    assert "CLAUDE_PLUGIN_ROOT" in text, f"{doc.name} must resolve the plugin root for a plugin-style install"
    assert _SKILL_DIR_HINT in text, (
        f"{doc.name} must point PYTHONPATH at the skill's own src/; the audited project has no copy of the engine"
    )


@pytest.mark.parametrize("doc", [SKILL, COMMANDS / "audit.md"])
def test_documented_invocation_does_not_discard_stderr(doc: Path) -> None:
    text = doc.read_text(encoding="utf-8")
    assert "2>/dev/null" not in text, (
        f"{doc.name} must not redirect stderr away: that is where the unenforced-.gitignore note "
        "and the third-party-root refusal are written"
    )


@pytest.mark.parametrize("doc", [SKILL, COMMANDS / "audit.md"])
def test_exit_codes_are_documented(doc: Path) -> None:
    text = doc.read_text(encoding="utf-8")
    assert "127" in text, f"{doc.name} must distinguish 'console script missing' from a refusal"
    assert "stderr" in text, f"{doc.name} must tell the model to read stderr"


# --- safety gates ---------------------------------------------------------


def test_fix_requires_explicit_approval_and_verifies() -> None:
    text = (COMMANDS / "fix.md").read_text(encoding="utf-8").lower()
    assert "approval" in text, "/todo:fix edits source files, so it must gate on explicit user approval"
    assert "wait for an answer" in text, "the approval gate must require waiting, not merely announcing intent"
    assert "verif" in text, "/todo:fix must run the project's checks rather than assume its edits are correct"


def test_fix_keeps_deferred_system_todos_in_the_code() -> None:
    text = (COMMANDS / "fix.md").read_text(encoding="utf-8")
    assert "leave its TODO comment" in text, (
        "a system fix deferred to CLAUDE.md is not resolved; deleting its comment loses the code location"
    )
    assert "`id`" in text, "CLAUDE.md deduplication must key on the stable id, not on a drifting file:line"


def test_analyze_reads_every_requirements_location() -> None:
    text = (COMMANDS / "analyze.md").read_text(encoding="utf-8")
    for location in (".claude/CLAUDE.md", "CLAUDE.local.md", ".claude/rules"):
        assert location in text, (
            f"/todo:analyze must look in {location}; Claude Code loads it, so a project may keep its rules there"
        )


def test_audit_handles_an_empty_result_and_bounds_its_reading() -> None:
    text = (COMMANDS / "audit.md").read_text(encoding="utf-8")
    assert "`0`" in text, "/todo:audit must say what to do when nothing is found, rather than inventing work"
    assert "summary" in text, "/todo:audit must read the summary block before the full array"
    assert "vocabulary" in text, "/todo:audit must take the difficulty labels from the payload, not from memory"


def test_audit_specifies_a_real_markdown_table() -> None:
    text = (COMMANDS / "audit.md").read_text(encoding="utf-8")
    assert "| # | TODO(s) | Location | Symbol | Diff. | Kind | Summary |" in text, (
        "the exact column header must be given: asking for 'a table row' without one is what let the model "
        "emit `Field: value` blocks instead"
    )
    assert "| - | ------- |" in text, "a pipe table needs its header separator row shown, or the output will not render"
    assert "Field: value" in text, (
        "the key-value shape the model actually produced must be named as the wrong answer, not merely implied"
    )
    assert "single-line" in text, "cells must be required to stay single-line, or long prose breaks the alignment"


def test_audit_requires_reasoning_behind_each_fix() -> None:
    text = (COMMANDS / "audit.md").read_text(encoding="utf-8")
    for heading in ("**Change:**", "**Why:**", "**Risk:**", "**Verify:**"):
        assert heading in text, (
            f"a fix proposal must cover {heading.strip('*:')}; a bare imperative gives the user no basis to approve"
        )
    assert "rejected" in text, "a considered-and-rejected alternative is the most useful part of a design proposal"


def test_audit_carries_a_worked_example_of_both_shapes() -> None:
    text = (COMMANDS / "audit.md").read_text(encoding="utf-8")
    assert "Worked example" in text, "models follow a demonstrated shape far more reliably than a described one"
    example = text.split("Worked example", 1)[1]
    assert "| 1 |" in example, "the example must show real table rows"
    assert "#### 1." in example, "the example must show the per-task detail block that pairs with those rows"


def test_skill_states_the_audit_output_contract() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert "Audit output shape" in text, (
        "the output contract belongs in SKILL.md too: the skill can be invoked without the slash command"
    )
    assert "Diff." in text and "Summary" in text, "SKILL.md must name the table's columns"


def test_audit_is_declared_read_only() -> None:
    text = (COMMANDS / "audit.md").read_text(encoding="utf-8")
    assert "allowed-tools:" in text, (
        "/todo:audit is read-only, so the restriction belongs in frontmatter where it is enforced, not only in prose"
    )
    assert "Edit" not in text.split("---")[1], "the audit command must not be granted an editing tool"


# --- documentation content ------------------------------------------------


def test_every_command_declares_a_description() -> None:
    for command in sorted(COMMANDS.glob("*.md")):
        text = command.read_text(encoding="utf-8")
        assert text.startswith("---"), f"{command.name} needs frontmatter for Claude Code to register the command"
        block = text[3 : text.index("\n---", 3)]
        assert "description:" in block, f"{command.name} needs a description; it is what the command menu shows"


def test_readme_documents_the_optional_gitignore_dependency() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "pip install pathspec" in readme, (
        "the engine runs on the system python3, which usually lacks pathspec; "
        "the README must tell users how to enable .gitignore support"
    )


def test_readme_credits_the_full_author_name() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "Ákos Jakub (arathus)" in readme, "the README must credit the same author name as the package manifests"


def test_new_marker_keywords_are_documented() -> None:
    for doc in (SKILL, REPO / "README.md", COMMANDS / "audit.md"):
        text = doc.read_text(encoding="utf-8")
        for keyword in ("FIXME", "HACK", "XXX"):
            assert keyword in text, (
                f"{doc.name} does not document {keyword}; a recognized keyword must be discoverable from the docs"
            )
