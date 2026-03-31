import pytest

from atlassian_local_cli.config import Config, reset_config


@pytest.fixture(autouse=True)
def _clean_config():
    """Reset config cache between tests."""
    reset_config()
    yield
    reset_config()


@pytest.fixture
def mock_config():
    return Config(
        wiki_url="https://wiki.test.com/",
        wiki_username="testuser",
        wiki_token="test-token",
        jira_url="https://jira.test.com/",
        jira_token="jira-test-token",
        jira_epic_name_field=None,
        jira_epic_link_field=None,
    )
