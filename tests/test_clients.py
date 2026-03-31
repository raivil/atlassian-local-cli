from unittest.mock import patch

import pytest

from atlassian_local_cli.clients import create_confluence, create_jira
from atlassian_local_cli.config import Config


class TestCreateConfluence:
    @patch("atlassian_local_cli.clients.Confluence")
    def test_basic_auth(self, mock_cls, mock_config):
        create_confluence(mock_config)
        mock_cls.assert_called_once_with(
            url="https://wiki.test.com/",
            username="testuser",
            password="test-token",
        )

    @patch("atlassian_local_cli.clients.Confluence")
    def test_bearer_auth(self, mock_cls):
        config = Config(
            wiki_url="https://wiki.test.com/",
            wiki_username=None,
            wiki_token="bearer-token",
            jira_url=None,
            jira_token=None,
            jira_epic_name_field=None,
            jira_epic_link_field=None,
        )
        create_confluence(config)
        _, kwargs = mock_cls.call_args
        assert kwargs["url"] == "https://wiki.test.com/"
        assert "session" in kwargs
        assert kwargs["session"].headers["Authorization"] == "Bearer bearer-token"

    def test_no_token_exits(self):
        config = Config(
            wiki_url="https://wiki.test.com/",
            wiki_username=None,
            wiki_token=None,
            jira_url=None,
            jira_token=None,
            jira_epic_name_field=None,
            jira_epic_link_field=None,
        )
        with pytest.raises(SystemExit):
            create_confluence(config)


class TestCreateJira:
    @patch("atlassian_local_cli.clients.Jira")
    def test_bearer_auth(self, mock_cls, mock_config):
        create_jira(mock_config)
        _, kwargs = mock_cls.call_args
        assert kwargs["url"] == "https://jira.test.com/"
        assert kwargs["session"].headers["Authorization"] == "Bearer jira-test-token"

    def test_missing_url_exits(self):
        config = Config(
            wiki_url="https://wiki.test.com/",
            wiki_username=None,
            wiki_token=None,
            jira_url=None,
            jira_token="token",
            jira_epic_name_field=None,
            jira_epic_link_field=None,
        )
        with pytest.raises(SystemExit):
            create_jira(config)

    def test_missing_token_exits(self):
        config = Config(
            wiki_url="https://wiki.test.com/",
            wiki_username=None,
            wiki_token=None,
            jira_url="https://jira.test.com/",
            jira_token=None,
            jira_epic_name_field=None,
            jira_epic_link_field=None,
        )
        with pytest.raises(SystemExit):
            create_jira(config)
