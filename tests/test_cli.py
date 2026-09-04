import sys
from unittest.mock import patch

import pytest

from atlassian_local_cli.cli import main


class TestCliParsing:
    def test_no_command_exits(self):
        with pytest.raises(SystemExit):
            sys.argv = ["atlassian-local-cli"]
            main()

    def test_help_exits(self):
        with pytest.raises(SystemExit) as exc_info:
            sys.argv = ["atlassian-local-cli", "--help"]
            main()
        assert exc_info.value.code == 0

    @pytest.mark.parametrize("flag", ["--version", "-v"])
    def test_version_flag_exits_zero_and_prints_version(self, flag, capsys):
        with pytest.raises(SystemExit) as exc_info:
            sys.argv = ["atlassian-local-cli", flag]
            main()
        assert exc_info.value.code == 0
        assert "atlassian-local-cli" in capsys.readouterr().out

    @patch("atlassian_local_cli.cli.jira_get")
    def test_dispatch_calls_handler(self, mock_handler):
        sys.argv = ["atlassian-local-cli", "jira-get", "PROJ-1"]
        main()
        mock_handler.assert_called_once()

    @patch("atlassian_local_cli.cli.wiki_attachments")
    def test_wiki_attachments_parses_flags(self, mock_handler):
        sys.argv = ["atlassian-local-cli", "wiki-attachments", "12345", "-o", "att", "--match", "*.txt"]
        main()
        args = mock_handler.call_args[0][0]
        assert args.page_id == "12345"
        assert args.output == "att"
        assert args.match == "*.txt"
        assert args.json is False
