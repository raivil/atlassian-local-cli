import sys

import requests
from atlassian import Confluence, Jira

from .config import CONFIG_DIR, get_config


def create_confluence(config=None):
    config = config or get_config()
    if not config.wiki_token:
        print(f"Error: WIKI_TOKEN is not set. Add it to {CONFIG_DIR / '.env'} or export it.", file=sys.stderr)
        sys.exit(1)
    if config.wiki_username:
        return Confluence(url=config.wiki_url, username=config.wiki_username, password=config.wiki_token)
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {config.wiki_token}"
    return Confluence(url=config.wiki_url, session=session)


def create_jira(config=None):
    config = config or get_config()
    if not config.jira_url or not config.jira_token:
        print(f"Error: JIRA_URL and JIRA_TOKEN must be set. Add them to {CONFIG_DIR / '.env'} or export them.", file=sys.stderr)
        sys.exit(1)
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {config.jira_token}"
    return Jira(url=config.jira_url, session=session)
