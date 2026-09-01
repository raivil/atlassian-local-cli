"""Tests for the multi-context (multi-account) configuration system."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from dotenv import dotenv_values

from atlassian_local_cli import cli as cli_module
from atlassian_local_cli import config as config_module
from atlassian_local_cli.cli import main
from atlassian_local_cli.config import (
    DEFAULT_CONTEXT_NAME,
    DEFAULT_WIKI_URL,
    ContextExistsError,
    ContextNotFoundError,
    InvalidContextNameError,
    context_env_path,
    context_exists,
    get_config,
    get_current_context,
    list_contexts,
    load_config,
    resolve_context_name,
    set_active_context,
    set_current_context,
    validate_context_name,
    write_context_env,
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

    def test_context_show_includes_jira_username(self, config_root, capsys):
        write_env(
            config_root / "contexts" / "cloud.env",
            JIRA_URL="https://acme.atlassian.net",
            JIRA_USERNAME="me@example.com",
            JIRA_TOKEN="t",
        )
        sys.argv = ["atlassian-local-cli", "context", "show", "cloud"]
        main()
        assert "JIRA_USERNAME=me@example.com" in capsys.readouterr().out

    def test_context_unset_clears_persisted(self, config_root, capsys):
        write_env(config_root / "contexts" / "work.env", JIRA_TOKEN="w")
        set_current_context("work")
        with patch("sys.argv", ["atlassian-local-cli", "context", "unset"]):
            main()
        assert get_current_context() is None


class TestValidateContextName:
    @pytest.mark.parametrize("name", ["work", "personal", "acme-corp", "a.b_c", "v2"])
    def test_accepts_safe_names(self, name):
        assert validate_context_name(name) == name

    @pytest.mark.parametrize(
        "name", ["", "   ", "../evil", "a/b", "a\\b", ".hidden", "has space", "sh*t", "a\nb"]
    )
    def test_rejects_unsafe_names(self, name):
        with pytest.raises(InvalidContextNameError):
            validate_context_name(name)

    def test_strips_surrounding_whitespace(self):
        assert validate_context_name("  work  ") == "work"


class TestWriteContextEnv:
    def test_named_context_lands_in_contexts_dir(self, config_root):
        path = write_context_env("work", {"JIRA_TOKEN": "abc"})
        assert path == config_root / "contexts" / "work.env"
        assert path.exists()

    def test_default_context_writes_dot_env(self, config_root):
        path = write_context_env(DEFAULT_CONTEXT_NAME, {"JIRA_TOKEN": "abc"})
        assert path == config_root / ".env"

    def test_written_file_is_owner_read_write_only(self, config_root):
        path = write_context_env("work", {"JIRA_TOKEN": "abc"})
        assert path.stat().st_mode & 0o777 == 0o600

    def test_contexts_dir_is_owner_only(self, config_root):
        write_context_env("work", {"JIRA_TOKEN": "abc"})
        assert (config_root / "contexts").stat().st_mode & 0o777 == 0o700

    def test_values_round_trip_through_dotenv(self, config_root):
        values = {
            "JIRA_URL": "https://jira.example.com/",
            "JIRA_TOKEN": 'tok"with#quote and space',
            "WIKI_TOKEN": "back\\slash",
        }
        path = write_context_env("work", values)
        assert dotenv_values(path) == values

    def test_blank_values_are_omitted(self, config_root):
        path = write_context_env("work", {"JIRA_TOKEN": "abc", "WIKI_TOKEN": "", "WIKI_URL": None})
        assert dotenv_values(path) == {"JIRA_TOKEN": "abc"}

    def test_newline_in_value_rejected(self, config_root):
        with pytest.raises(ValueError):
            write_context_env("work", {"JIRA_TOKEN": "a\nb"})

    def test_refuses_to_clobber_existing_context(self, config_root):
        write_context_env("work", {"JIRA_TOKEN": "first"})
        with pytest.raises(ContextExistsError):
            write_context_env("work", {"JIRA_TOKEN": "second"})
        assert dotenv_values(config_root / "contexts" / "work.env") == {"JIRA_TOKEN": "first"}

    def test_force_overwrites(self, config_root):
        write_context_env("work", {"JIRA_TOKEN": "first"})
        write_context_env("work", {"JIRA_TOKEN": "second"}, force=True)
        assert dotenv_values(config_root / "contexts" / "work.env") == {"JIRA_TOKEN": "second"}

    def test_new_context_is_listed_and_loadable(self, config_root):
        write_context_env("work", {"JIRA_URL": "https://j.example.com", "JIRA_TOKEN": "abc"})
        assert "work" in list_contexts()
        assert load_config(context="work").jira_token == "abc"

    def test_rejects_unsafe_name(self, config_root):
        with pytest.raises(InvalidContextNameError):
            write_context_env("../escape", {"JIRA_TOKEN": "abc"})
        assert not (config_root.parent / "escape.env").exists()


class TestContextAddCli:
    def _run(self, *argv):
        sys.argv = ["atlassian-local-cli", "context", "add", *argv]
        main()

    def test_flags_only_writes_file(self, config_root, capsys):
        self._run(
            "work",
            "--jira-url", "https://jira.example.com",
            "--jira-username", "me@example.com",
            "--jira-token", "jtok",
            "--wiki-url", "https://wiki.example.com/",
            "--wiki-username", "me",
            "--wiki-token", "wtok",
        )
        assert dotenv_values(config_root / "contexts" / "work.env") == {
            "WIKI_URL": "https://wiki.example.com/",
            "WIKI_USERNAME": "me",
            "WIKI_TOKEN": "wtok",
            "JIRA_URL": "https://jira.example.com",
            "JIRA_USERNAME": "me@example.com",
            "JIRA_TOKEN": "jtok",
        }
        assert "work" in capsys.readouterr().out

    def test_prompts_for_missing_values(self, config_root, monkeypatch, capsys):
        answers = iter(
            ["https://wiki.example.com/", "me", "https://jira.example.com", "me@example.com"]
        )
        secrets = iter(["wtok", "jtok"])
        monkeypatch.setattr("builtins.input", lambda *a: next(answers))
        monkeypatch.setattr(cli_module.getpass, "getpass", lambda *a: next(secrets))
        monkeypatch.setattr(cli_module.sys.stdin, "isatty", lambda: True)
        self._run("work")
        assert dotenv_values(config_root / "contexts" / "work.env") == {
            "WIKI_URL": "https://wiki.example.com/",
            "WIKI_USERNAME": "me",
            "WIKI_TOKEN": "wtok",
            "JIRA_URL": "https://jira.example.com",
            "JIRA_USERNAME": "me@example.com",
            "JIRA_TOKEN": "jtok",
        }

    def test_blank_prompt_answer_uses_wiki_url_default(self, config_root, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda *a: "")
        monkeypatch.setattr(cli_module.getpass, "getpass", lambda *a: "tok")
        monkeypatch.setattr(cli_module.sys.stdin, "isatty", lambda: True)
        self._run("work")
        assert dotenv_values(config_root / "contexts" / "work.env")["WIKI_URL"] == DEFAULT_WIKI_URL

    def test_non_tty_never_blocks_on_a_prompt(self, config_root, monkeypatch):
        """CI has no one to answer prompts; omitted values take their defaults."""
        monkeypatch.setattr(cli_module.sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("prompted in non-tty"))
        self._run("work", "--jira-token", "jtok")
        assert dotenv_values(config_root / "contexts" / "work.env") == {
            "WIKI_URL": DEFAULT_WIKI_URL,
            "JIRA_TOKEN": "jtok",
        }

    def test_non_tty_with_nothing_supplied_exits(self, config_root, monkeypatch, capsys):
        monkeypatch.setattr(cli_module.sys.stdin, "isatty", lambda: False)
        with pytest.raises(SystemExit) as exc:
            self._run("work")
        assert exc.value.code == 1
        assert "token" in capsys.readouterr().err.lower()
        assert not (config_root / "contexts" / "work.env").exists()

    def test_exits_when_no_token_supplied(self, config_root, capsys):
        with pytest.raises(SystemExit) as exc:
            self._run("work", "--jira-url", "https://jira.example.com", "--jira-token", "")
        assert exc.value.code == 1
        assert "token" in capsys.readouterr().err.lower()
        assert not (config_root / "contexts" / "work.env").exists()

    def test_existing_context_exits_with_hint(self, config_root, capsys):
        write_context_env("work", {"JIRA_TOKEN": "first"})
        with pytest.raises(SystemExit) as exc:
            self._run("work", "--jira-token", "second")
        assert exc.value.code == 1
        assert "--force" in capsys.readouterr().err

    def test_force_flag_overwrites(self, config_root):
        write_context_env("work", {"JIRA_TOKEN": "first"})
        self._run("work", "--jira-token", "second", "--force")
        assert dotenv_values(config_root / "contexts" / "work.env")["JIRA_TOKEN"] == "second"

    def test_invalid_name_exits(self, config_root, capsys):
        with pytest.raises(SystemExit) as exc:
            self._run("../evil", "--jira-token", "x")
        assert exc.value.code == 1
        assert "name" in capsys.readouterr().err.lower()

    def test_warns_when_shell_env_shadows_written_keys(self, config_root, monkeypatch, capsys):
        monkeypatch.setenv("JIRA_TOKEN", "shadow")
        self._run("work", "--jira-token", "jtok")
        err = capsys.readouterr().err
        assert "JIRA_TOKEN" in err
        assert "shell" in err.lower()

    def test_does_not_switch_active_context(self, config_root, capsys):
        self._run("work", "--jira-token", "jtok")
        assert get_current_context() is None
        assert "context use work" in capsys.readouterr().out

    @pytest.mark.parametrize("interrupt", [EOFError, KeyboardInterrupt])
    def test_cancelling_a_prompt_exits_cleanly(self, config_root, monkeypatch, capsys, interrupt):
        """Ctrl-D / Ctrl-C at a prompt should not dump a traceback."""
        def boom(*a):
            raise interrupt()
        monkeypatch.setattr("builtins.input", boom)
        monkeypatch.setattr(cli_module.sys.stdin, "isatty", lambda: True)
        with pytest.raises(SystemExit) as exc:
            self._run("work")
        assert exc.value.code == 1
        assert "cancelled" in capsys.readouterr().err.lower()
        assert not (config_root / "contexts" / "work.env").exists()

    def test_jira_username_enables_cloud_basic_auth(self, config_root):
        """Cloud accounts need email+token basic auth, so the email must be storable."""
        self._run("cloud", "--jira-url", "https://acme.atlassian.net", "--jira-username",
                  "me@example.com", "--jira-token", "t")
        assert load_config(context="cloud").jira_username == "me@example.com"

    def test_epic_fields_are_flag_only(self, config_root):
        self._run("work", "--jira-token", "t", "--jira-epic-link-field", "customfield_10014")
        written = dotenv_values(config_root / "contexts" / "work.env")
        assert written["JIRA_EPIC_LINK_FIELD"] == "customfield_10014"
        assert "JIRA_EPIC_NAME_FIELD" not in written
