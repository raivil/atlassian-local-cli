import sys
from urllib.parse import urlparse

import requests
from atlassian import Confluence, Jira

from .config import context_env_path, get_config


CLOUD_HOST_SUFFIX = ".atlassian.net"


def _is_cloud_host(url) -> bool:
    return (urlparse(url or "").hostname or "").endswith(CLOUD_HOST_SUFFIX)


def _auth_override(value, env_key) -> str | None:
    """Validate an explicit basic|bearer choice from JIRA_AUTH / WIKI_AUTH."""
    if not value:
        return None
    choice = value.strip().lower()
    if choice not in ("basic", "bearer"):
        print(f"Error: {env_key} must be 'basic' or 'bearer', got {value!r}.", file=sys.stderr)
        sys.exit(1)
    return choice


def _bearer_session(token):
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"
    return session


def _jira_uses_basic_auth(config) -> bool:
    """Cloud wants email + API token over basic; Server/DC wants a Bearer PAT.

    Keyed off the URL, not the presence of JIRA_USERNAME — plenty of Server
    configs carry a stray username that must not flip them to basic auth.
    """
    override = _auth_override(config.jira_auth, "JIRA_AUTH")
    if override:
        return override == "basic"
    return _is_cloud_host(config.jira_url)


def _confluence_uses_basic_auth(config) -> bool:
    """Unlike Jira, a username has always selected basic auth here, so it still
    does — Confluence configs set WIKI_USERNAME deliberately. The URL check only
    adds the Cloud case, where a Bearer token is rejected outright.
    """
    override = _auth_override(config.wiki_auth, "WIKI_AUTH")
    if override:
        return override == "basic"
    return bool(config.wiki_username) or _is_cloud_host(config.wiki_url)


def create_confluence(config=None):
    config = config or get_config()
    if not config.wiki_token:
        path = context_env_path(config.context)
        print(f"Error: WIKI_TOKEN is not set for context '{config.context}'. Add it to {path} or export it.", file=sys.stderr)
        sys.exit(1)

    if not _confluence_uses_basic_auth(config):
        return Confluence(url=config.wiki_url, session=_bearer_session(config.wiki_token))

    if not config.wiki_username:
        path = context_env_path(config.context)
        if _is_cloud_host(config.wiki_url):
            print(
                f"Error: {config.wiki_url} looks like Atlassian Cloud, which needs basic auth. "
                f"Set WIKI_USERNAME (your account email) in {path}, or set WIKI_AUTH=bearer to force a PAT.",
                file=sys.stderr,
            )
        else:
            print(
                f"Error: WIKI_AUTH=basic needs WIKI_USERNAME. Add your account email to {path}, "
                "or unset WIKI_AUTH to use a Bearer PAT.",
                file=sys.stderr,
            )
        sys.exit(1)

    return Confluence(url=config.wiki_url, username=config.wiki_username, password=config.wiki_token)


def create_jira(config=None):
    config = config or get_config()
    if not config.jira_url or not config.jira_token:
        path = context_env_path(config.context)
        print(f"Error: JIRA_URL and JIRA_TOKEN must be set for context '{config.context}'. Add them to {path} or export them.", file=sys.stderr)
        sys.exit(1)
    if not _jira_uses_basic_auth(config):
        return Jira(url=config.jira_url, session=_bearer_session(config.jira_token))

    if not config.jira_username:
        path = context_env_path(config.context)
        print(
            f"Error: {config.jira_url} looks like Atlassian Cloud, which needs basic auth. "
            f"Set JIRA_USERNAME (your account email) in {path}, or set JIRA_AUTH=bearer to force a PAT.",
            file=sys.stderr,
        )
        sys.exit(1)
    return Jira(url=config.jira_url, username=config.jira_username, password=config.jira_token)
