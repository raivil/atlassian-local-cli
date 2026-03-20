import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

CONFIG_DIR = Path.home() / ".config" / "atlassian-local-cli"


@dataclass(frozen=True)
class Config:
    wiki_url: str
    wiki_username: str | None
    wiki_token: str | None
    jira_url: str | None
    jira_token: str | None


_config: Config | None = None


def load_config(env_file: Path | None = None) -> Config:
    load_dotenv(env_file or (CONFIG_DIR / ".env"))
    return Config(
        wiki_url=os.getenv("WIKI_URL", "https://wiki.example.com/"),
        wiki_username=os.getenv("WIKI_USERNAME"),
        wiki_token=os.getenv("WIKI_TOKEN"),
        jira_url=os.getenv("JIRA_URL"),
        jira_token=os.getenv("JIRA_TOKEN"),
    )


def get_config() -> Config:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config():
    global _config
    _config = None
