import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

CONFIG_DIR = Path.home() / ".config" / "atlassian-local-cli"
CONTEXTS_DIR = CONFIG_DIR / "contexts"
CURRENT_CONTEXT_FILE = CONFIG_DIR / "current-context"
DEFAULT_CONTEXT_NAME = "default"
DEFAULT_WIKI_URL = "https://wiki.example.com/"

# Context names become filenames; keep them boring so they can't escape CONTEXTS_DIR.
_VALID_CONTEXT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ContextNotFoundError(Exception):
    pass


class ContextExistsError(Exception):
    pass


class InvalidContextNameError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    wiki_url: str
    wiki_username: str | None
    wiki_token: str | None
    jira_url: str | None
    jira_token: str | None
    jira_epic_name_field: str | None
    jira_epic_link_field: str | None
    jira_username: str | None = None
    jira_auth: str | None = None
    wiki_auth: str | None = None
    context: str = DEFAULT_CONTEXT_NAME


_config: Config | None = None
_active_context: str | None = None


def validate_context_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not _VALID_CONTEXT_NAME.match(cleaned):
        raise InvalidContextNameError(
            f"Invalid context name {name!r}. Use letters, digits, '.', '_' or '-', "
            "starting with a letter or digit."
        )
    return cleaned


def context_env_path(name: str) -> Path:
    if name == DEFAULT_CONTEXT_NAME:
        return CONFIG_DIR / ".env"
    return CONTEXTS_DIR / f"{name}.env"


def list_contexts() -> list[str]:
    names: list[str] = []
    if (CONFIG_DIR / ".env").exists():
        names.append(DEFAULT_CONTEXT_NAME)
    if CONTEXTS_DIR.exists():
        for p in sorted(CONTEXTS_DIR.glob("*.env")):
            if p.stem != DEFAULT_CONTEXT_NAME:
                names.append(p.stem)
    return names


def context_exists(name: str) -> bool:
    return context_env_path(name).exists()


def get_current_context() -> str | None:
    if not CURRENT_CONTEXT_FILE.exists():
        return None
    name = CURRENT_CONTEXT_FILE.read_text().strip()
    return name or None


def set_current_context(name: str | None) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if name is None:
        if CURRENT_CONTEXT_FILE.exists():
            CURRENT_CONTEXT_FILE.unlink()
        return
    CURRENT_CONTEXT_FILE.write_text(name + "\n")


def set_active_context(name: str | None) -> None:
    """Override the active context for this process. Clears cached config."""
    global _active_context, _config
    _active_context = name
    _config = None


def resolve_context_name() -> str:
    if _active_context is not None:
        return _active_context
    persisted = get_current_context()
    if persisted is not None:
        return persisted
    return DEFAULT_CONTEXT_NAME


def load_config(env_file: Path | str | None = None, context: str | None = None) -> Config:
    if env_file is not None:
        path = Path(env_file)
        name = context or DEFAULT_CONTEXT_NAME
    else:
        name = context or resolve_context_name()
        path = context_env_path(name)
        # Only error on explicit non-default contexts; missing .env is fine
        # (env vars from the shell may still satisfy required settings).
        if name != DEFAULT_CONTEXT_NAME and not path.exists():
            available = ", ".join(list_contexts()) or "(none)"
            raise ContextNotFoundError(
                f"Context '{name}' not found at {path}. Available: {available}"
            )

    values = dotenv_values(path) if path.exists() else {}

    def get(key: str, default: str | None = None) -> str | None:
        # Shell env var wins over file value, matching prior behavior.
        return os.getenv(key) or values.get(key) or default

    return Config(
        wiki_url=get("WIKI_URL", DEFAULT_WIKI_URL) or DEFAULT_WIKI_URL,
        wiki_username=get("WIKI_USERNAME"),
        wiki_token=get("WIKI_TOKEN"),
        jira_url=get("JIRA_URL"),
        jira_token=get("JIRA_TOKEN"),
        jira_epic_name_field=get("JIRA_EPIC_NAME_FIELD"),
        jira_epic_link_field=get("JIRA_EPIC_LINK_FIELD"),
        jira_username=get("JIRA_USERNAME"),
        jira_auth=get("JIRA_AUTH"),
        wiki_auth=get("WIKI_AUTH"),
        context=name,
    )


def _env_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def write_context_env(name: str, values: dict[str, str | None], force: bool = False) -> Path:
    """Write a context's .env file. Returns the path written."""
    name = validate_context_name(name)
    path = context_env_path(name)
    if path.exists() and not force:
        raise ContextExistsError(f"Context '{name}' already exists at {path}")

    present = {k: v for k, v in values.items() if v}
    for key, value in present.items():
        if "\n" in value or "\r" in value:
            raise ValueError(f"{key} must not contain newlines")

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    body = "".join(f"{k}={_env_quote(v)}\n" for k, v in present.items())
    path.write_text(body)
    path.chmod(0o600)
    return path


def get_config() -> Config:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config() -> None:
    global _config, _active_context
    _config = None
    _active_context = None
