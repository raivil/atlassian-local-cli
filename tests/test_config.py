from atlassian_local_cli.config import get_config, load_config, reset_config


class TestConfig:
    def test_load_config_defaults(self, monkeypatch):
        monkeypatch.delenv("WIKI_URL", raising=False)
        monkeypatch.delenv("WIKI_USERNAME", raising=False)
        monkeypatch.delenv("WIKI_TOKEN", raising=False)
        monkeypatch.delenv("JIRA_URL", raising=False)
        monkeypatch.delenv("JIRA_TOKEN", raising=False)
        config = load_config(env_file="/dev/null")
        assert config.wiki_url == "https://wiki.example.com/"
        assert config.wiki_username is None
        assert config.wiki_token is None
        assert config.jira_url is None
        assert config.jira_token is None

    def test_load_config_from_env(self, monkeypatch):
        monkeypatch.setenv("WIKI_URL", "https://custom.wiki/")
        monkeypatch.setenv("WIKI_USERNAME", "myuser")
        monkeypatch.setenv("WIKI_TOKEN", "mytoken")
        monkeypatch.setenv("JIRA_URL", "https://jira.test/")
        monkeypatch.setenv("JIRA_TOKEN", "jiratoken")
        config = load_config(env_file="/dev/null")
        assert config.wiki_url == "https://custom.wiki/"
        assert config.wiki_username == "myuser"
        assert config.wiki_token == "mytoken"
        assert config.jira_url == "https://jira.test/"
        assert config.jira_token == "jiratoken"

    def test_get_config_caches(self, monkeypatch):
        monkeypatch.setenv("WIKI_TOKEN", "token1")
        config1 = get_config()
        monkeypatch.setenv("WIKI_TOKEN", "token2")
        config2 = get_config()
        assert config1 is config2

    def test_reset_config_clears_cache(self, monkeypatch):
        monkeypatch.setenv("WIKI_TOKEN", "token1")
        config1 = get_config()
        reset_config()
        monkeypatch.setenv("WIKI_TOKEN", "token2")
        config2 = get_config()
        assert config1 is not config2
