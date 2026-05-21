import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

CONFIG_DIR = Path.home() / ".config" / "atlassian-local-cli"
CONTEXTS_DIR = CONFIG_DIR / "contexts"
CURRENT_CONTEXT_FILE = CONFIG_DIR / "current-context"
DEFAULT_CONTEXT_NAME = "default"


class ContextNotFoundError(Exception):
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
    context: str = DEFAULT_CONTEXT_NAME


_config: Config | None = None
_active_context: str | None = None


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
        wiki_url=get("WIKI_URL", "https://wiki.example.com/") or "https://wiki.example.com/",
        wiki_username=get("WIKI_USERNAME"),
        wiki_token=get("WIKI_TOKEN"),
        jira_url=get("JIRA_URL"),
        jira_token=get("JIRA_TOKEN"),
        jira_epic_name_field=get("JIRA_EPIC_NAME_FIELD"),
        jira_epic_link_field=get("JIRA_EPIC_LINK_FIELD"),
        context=name,
    )


def get_config() -> Config:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config() -> None:
    global _config, _active_context
    _config = None
    _active_context = None
