"""Guards against drift between the CLI, the Makefile and the docs.

Every one of these caught a real inconsistency when it was written; they exist so
a new subcommand can't be added without its make target and documentation.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = (ROOT / "Makefile").read_text()
CLI_SOURCE = (ROOT / "src" / "atlassian_local_cli" / "cli.py").read_text()

SUBCOMMANDS = sorted(set(re.findall(r'subparsers\.add_parser\("([^"]+)"', CLI_SOURCE)))
MAKE_TARGETS = sorted(set(re.findall(r"^([a-z][a-z0-9-]*):", MAKEFILE, re.M)))
PHONY = set(re.search(r"^\.PHONY:(.*)$", MAKEFILE, re.M).group(1).split())


def test_every_make_target_is_phony():
    assert sorted(set(MAKE_TARGETS) - PHONY) == []


def test_phony_lists_no_targets_that_do_not_exist():
    assert sorted(PHONY - set(MAKE_TARGETS)) == []


def test_every_recipe_honours_the_context_variable():
    """Recipes must call $(CLI); a bare `uv run atlassian-local-cli` silently
    ignores CONTEXT=<name>, which every target is documented as accepting."""
    bare = [
        line.strip()
        for line in MAKEFILE.splitlines()
        if "uv run atlassian-local-cli" in line and not line.startswith("CLI =")
    ]
    assert bare == []


@pytest.mark.parametrize("subcommand", SUBCOMMANDS)
def test_subcommand_has_a_make_target(subcommand):
    if subcommand == "context":  # exposed as context-list, context-use, ...
        pytest.skip("dispatches to context-* targets")
    assert subcommand in MAKE_TARGETS


@pytest.mark.parametrize("doc", ["README.md", "CLAUDE.md"])
def test_every_subcommand_is_documented(doc):
    text = (ROOT / doc).read_text()
    assert [c for c in SUBCOMMANDS if c not in text] == []


def test_ds_store_is_ignored():
    """macOS drops these into the tree; without the rule they show up in every
    `git status` and eventually get committed by an `add -A`."""
    assert ".DS_Store" in (ROOT / ".gitignore").read_text()


def test_changelog_documents_the_current_version():
    """A release is cut from the tag, so a version bump without a matching
    CHANGELOG entry ships an undocumented release."""
    version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)
    latest = re.search(r"^## v([0-9.]+)", (ROOT / "CHANGELOG.md").read_text(), re.M).group(1)
    assert latest == version


CONFIG_SOURCE = (ROOT / "src" / "atlassian_local_cli" / "config.py").read_text()
ENV_KEYS = sorted(set(re.findall(r'\bget\("([A-Z_]+)"', CONFIG_SOURCE)))


def test_config_reads_at_least_the_known_keys():
    """Sanity check on the parse above, so the next test can't pass vacuously."""
    assert {"WIKI_URL", "WIKI_TOKEN", "JIRA_TOKEN", "WIKI_AUTH", "JIRA_AUTH"} <= set(ENV_KEYS)


def test_every_env_key_is_documented_in_the_example():
    """WIKI_AUTH shipped in v2.10.0 and went undocumented until v2.12.1, because
    nothing tied load_config's keys to the file users copy from."""
    example = (ROOT / ".env.example").read_text()
    missing = [key for key in ENV_KEYS if key not in example]
    assert missing == [], f"undocumented in .env.example: {missing}"
