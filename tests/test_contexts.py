"""Tests for the multi-context (multi-account) configuration system."""

from pathlib import Path
from unittest.mock import patch

import pytest

from atlassian_local_cli import config as config_module
from atlassian_local_cli.cli import main
from atlassian_local_cli.config import (
    DEFAULT_CONTEXT_NAME,
    ContextNotFoundError,
    context_env_path,
    context_exists,
    get_config,
    get_current_context,
    list_contexts,
    load_config,
    resolve_context_name,
    set_active_context,
    set_current_context,
)


@pytest.fixture
def config_root(tmp_path, monkeypatch):
    """Redirect CONFIG_DIR/CONTEXTS_DIR/CURRENT_CONTEXT_FILE to a temp dir."""
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONTEXTS_DIR", tmp_path / "contexts")
    monkeypatch.setattr(config_module, "CURRENT_CONTEXT_FILE", tmp_path / "current-context")
    # Strip the env vars so file contents are what we test.
    for var in ("WIKI_URL", "WIKI_USERNAME", "WIKI_TOKEN", "JIRA_URL", "JIRA_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    yield tmp_path


def write_env(path: Path, **values):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in values.items()]
    path.write_text("\n".join(lines) + "\n")


class TestPaths:
    def test_default_context_maps_to_dot_env(self, config_root):
        assert context_env_path(DEFAULT_CONTEXT_NAME) == config_root / ".env"

    def test_named_context_maps_to_contexts_dir(self, config_root):
        assert context_env_path("work") == config_root / "contexts" / "work.env"


class TestListContexts:
    def test_empty_when_no_files(self, config_root):
        assert list_contexts() == []

    def test_includes_default_when_dot_env_exists(self, config_root):
        write_env(config_root / ".env", JIRA_TOKEN="x")
        assert list_contexts() == ["default"]

    def test_includes_named_contexts_sorted(self, config_root):
        write_env(config_root / ".env", JIRA_TOKEN="x")
        write_env(config_root / "contexts" / "work.env", JIRA_TOKEN="w")
        write_env(config_root / "contexts" / "personal.env", JIRA_TOKEN="p")
        assert list_contexts() == ["default", "personal", "work"]

    def test_ignores_non_env_files(self, config_root):
        (config_root / "contexts").mkdir()
        (config_root / "contexts" / "notes.txt").write_text("ignored")
        assert list_contexts() == []


class TestResolution:
    def test_default_when_nothing_set(self, config_root):
        assert resolve_context_name() == "default"

    def test_persisted_overrides_default(self, config_root):
        set_current_context("work")
        assert resolve_context_name() == "work"
        assert get_current_context() == "work"

    def test_active_overrides_persisted(self, config_root):
        set_current_context("work")
        set_active_context("personal")
        assert resolve_context_name() == "personal"

    def test_unset_clears_persisted(self, config_root):
        set_current_context("work")
        set_current_context(None)
        assert get_current_context() is None
        assert resolve_context_name() == "default"


class TestLoadConfigByContext:
    def test_loads_named_context(self, config_root):
        write_env(config_root / "contexts" / "work.env",
                  JIRA_URL="https://work.jira/", JIRA_TOKEN="work-token")
        cfg = load_config(context="work")
        assert cfg.jira_url == "https://work.jira/"
        assert cfg.jira_token == "work-token"
        assert cfg.context == "work"

    def test_missing_named_context_raises(self, config_root):
        with pytest.raises(ContextNotFoundError, match="Context 'nope' not found"):
            load_config(context="nope")

    def test_missing_default_does_not_raise(self, config_root):
        # No .env file — should fall back to defaults rather than error.
        cfg = load_config()
        assert cfg.wiki_url == "https://wiki.example.com/"
        assert cfg.jira_token is None
        assert cfg.context == "default"

    def test_active_context_drives_get_config(self, config_root):
        write_env(config_root / ".env",
                  JIRA_URL="https://default.jira/", JIRA_TOKEN="default-token")
        write_env(config_root / "contexts" / "work.env",
                  JIRA_URL="https://work.jira/", JIRA_TOKEN="work-token")

        set_active_context("work")
        cfg = get_config()
        assert cfg.jira_token == "work-token"
        assert cfg.context == "work"

    def test_set_active_context_clears_cache(self, config_root):
        write_env(config_root / ".env", JIRA_TOKEN="a")
        write_env(config_root / "contexts" / "b.env", JIRA_TOKEN="b")
        cfg_a = get_config()
        assert cfg_a.jira_token == "a"
        set_active_context("b")
        cfg_b = get_config()
        assert cfg_b.jira_token == "b"
        assert cfg_a is not cfg_b

    def test_shell_env_still_overrides_file(self, config_root, monkeypatch):
        write_env(config_root / "contexts" / "work.env", JIRA_TOKEN="file-token")
        monkeypatch.setenv("JIRA_TOKEN", "shell-token")
        cfg = load_config(context="work")
        assert cfg.jira_token == "shell-token"


class TestContextExists:
    def test_default_when_dot_env_present(self, config_root):
        write_env(config_root / ".env", JIRA_TOKEN="x")
        assert context_exists("default")

    def test_default_false_without_dot_env(self, config_root):
        assert not context_exists("default")

    def test_named(self, config_root):
        assert not context_exists("work")
        write_env(config_root / "contexts" / "work.env", JIRA_TOKEN="x")
        assert context_exists("work")


class TestCliDispatch:
    """Smoke tests that --context wires through to set_active_context, and
    that the `context` subcommand handlers don't blow up."""

    def test_context_flag_for_unknown_context_exits(self, config_root, capsys):
        with pytest.raises(SystemExit):
            with patch("sys.argv", ["atlassian-local-cli", "--context", "nope", "context", "current"]):
                main()
        err = capsys.readouterr().err
        assert "nope" in err and "does not exist" in err

    def test_context_flag_activates_context(self, config_root, capsys):
        write_env(config_root / "contexts" / "work.env", JIRA_TOKEN="work-token")
        with patch("sys.argv", ["atlassian-local-cli", "--context", "work", "context", "current"]):
            main()
        assert capsys.readouterr().out.strip() == "work"

    def test_context_list_marks_active(self, config_root, capsys):
        write_env(config_root / ".env", JIRA_TOKEN="d")
        write_env(config_root / "contexts" / "work.env", JIRA_TOKEN="w")
        set_current_context("work")
        with patch("sys.argv", ["atlassian-local-cli", "context", "list"]):
            main()
        out = capsys.readouterr().out
        assert "* work" in out
        assert "  default" in out

    def test_context_use_persists_and_validates(self, config_root, capsys):
        write_env(config_root / "contexts" / "work.env", JIRA_TOKEN="w")
        with patch("sys.argv", ["atlassian-local-cli", "context", "use", "work"]):
            main()
        assert get_current_context() == "work"

        with pytest.raises(SystemExit):
            with patch("sys.argv", ["atlassian-local-cli", "context", "use", "missing"]):
                main()

    def test_context_show_masks_tokens(self, config_root, capsys):
        write_env(config_root / "contexts" / "work.env",
                  JIRA_URL="https://work.jira/", JIRA_TOKEN="supersecret-token-abc")
        with patch("sys.argv", ["atlassian-local-cli", "context", "show", "work"]):
            main()
        out = capsys.readouterr().out
        assert "supersecret-token-abc" not in out
        assert "https://work.jira/" in out

    def test_context_unset_clears_persisted(self, config_root, capsys):
        write_env(config_root / "contexts" / "work.env", JIRA_TOKEN="w")
        set_current_context("work")
        with patch("sys.argv", ["atlassian-local-cli", "context", "unset"]):
            main()
        assert get_current_context() is None
