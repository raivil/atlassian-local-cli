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
    def test_bearer_auth_when_no_username(self, mock_cls, mock_config):
        create_jira(mock_config)
        _, kwargs = mock_cls.call_args
        assert kwargs["url"] == "https://jira.test.com/"
        assert kwargs["session"].headers["Authorization"] == "Bearer jira-test-token"

    @staticmethod
    def _config(**overrides):
        base = dict(
            wiki_url="https://wiki.test.com/",
            wiki_username=None,
            wiki_token=None,
            jira_url="https://jira.test.com/",
            jira_token="token",
            jira_epic_name_field=None,
            jira_epic_link_field=None,
        )
        base.update(overrides)
        return Config(**base)

    @patch("atlassian_local_cli.clients.Jira")
    def test_cloud_url_uses_basic_auth(self, mock_cls):
        """Atlassian Cloud rejects Bearer; it wants email + API token via basic auth."""
        create_jira(self._config(
            jira_url="https://acme.atlassian.net/",
            jira_token="api-token",
            jira_username="me@example.com",
        ))
        mock_cls.assert_called_once_with(
            url="https://acme.atlassian.net/",
            username="me@example.com",
            password="api-token",
        )

    @patch("atlassian_local_cli.clients.Jira")
    def test_server_url_uses_bearer_even_when_username_set(self, mock_cls):
        """Server/DC PATs fail under basic auth, so a stray JIRA_USERNAME must not flip it."""
        create_jira(self._config(jira_username="jdoe", jira_token="pat"))
        _, kwargs = mock_cls.call_args
        assert kwargs["session"].headers["Authorization"] == "Bearer pat"
        assert "username" not in kwargs

    def test_cloud_url_without_username_exits_with_guidance(self, capsys):
        with pytest.raises(SystemExit):
            create_jira(self._config(jira_url="https://acme.atlassian.net/", jira_token="t"))
        assert "JIRA_USERNAME" in capsys.readouterr().err

    @patch("atlassian_local_cli.clients.Jira")
    def test_explicit_basic_overrides_url_detection(self, mock_cls):
        """Cloud on a custom domain still needs basic auth."""
        create_jira(self._config(
            jira_url="https://jira.acme.com/", jira_username="me@acme.com", jira_auth="basic"
        ))
        mock_cls.assert_called_once_with(
            url="https://jira.acme.com/", username="me@acme.com", password="token"
        )

    @patch("atlassian_local_cli.clients.Jira")
    def test_explicit_bearer_overrides_url_detection(self, mock_cls):
        create_jira(self._config(
            jira_url="https://acme.atlassian.net/", jira_username="me@acme.com", jira_auth="bearer"
        ))
        _, kwargs = mock_cls.call_args
        assert kwargs["session"].headers["Authorization"] == "Bearer token"

    def test_invalid_jira_auth_exits(self, capsys):
        with pytest.raises(SystemExit):
            create_jira(self._config(jira_auth="oauth"))
        assert "JIRA_AUTH" in capsys.readouterr().err

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
