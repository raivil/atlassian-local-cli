import io
import sys
from unittest.mock import patch

import pytest

from atlassian_local_cli.text_input import resolve_body


class TestResolveBody:
    def test_returns_inline_body(self):
        assert resolve_body("hello", None) == "hello"

    def test_reads_file(self, tmp_path):
        f = tmp_path / "body.md"
        f.write_text("from a file\n")
        assert resolve_body(None, str(f)) == "from a file\n"

    def test_reads_stdin_for_dash(self):
        with patch.object(sys, "stdin", io.StringIO("piped in")):
            assert resolve_body(None, "-") == "piped in"

    def test_rejects_both(self, capsys):
        with pytest.raises(SystemExit):
            resolve_body("inline", "file.md")
        assert "mutually exclusive" in capsys.readouterr().err

    def test_returns_none_when_neither_given(self):
        assert resolve_body(None, None) is None
