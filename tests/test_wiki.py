from argparse import Namespace
from unittest.mock import MagicMock, patch

from atlassian_local_cli.wiki import wiki_create, wiki_export, wiki_update

MOCK_PAGE = {
    "id": "12345",
    "title": "Test Page",
    "space": {"key": "DEV"},
    "version": {"number": 3, "when": "2026-03-20T10:00:00.000Z"},
    "history": {
        "createdBy": {"displayName": "Test Author"},
        "createdDate": "2026-01-01T00:00:00.000Z",
    },
    "body": {
        "export_view": {"value": "<p>Hello world</p>"},
        "storage": {"value": "<p>Hello world</p>"},
    },
}


class TestWikiExport:
    @patch("atlassian_local_cli.wiki.get_config")
    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_stdout(self, mock_create, mock_config, capsys):
        mock_config.return_value = MagicMock(wiki_url="https://wiki.test.com/")
        mock_confluence = MagicMock()
        mock_confluence.get_page_by_id.return_value = MOCK_PAGE
        mock_create.return_value = mock_confluence

        wiki_export(Namespace(page_id="12345", output=None))
        output = capsys.readouterr().out
        assert "# Test Page" in output
        assert "Hello world" in output

    @patch("atlassian_local_cli.wiki.get_config")
    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_to_file(self, mock_create, mock_config, tmp_path):
        mock_config.return_value = MagicMock(wiki_url="https://wiki.test.com/")
        mock_confluence = MagicMock()
        mock_confluence.get_page_by_id.return_value = MOCK_PAGE
        mock_create.return_value = mock_confluence

        outfile = str(tmp_path / "out.md")
        wiki_export(Namespace(page_id="12345", output=outfile))
        content = (tmp_path / "out.md").read_text()
        assert "# Test Page" in content

    @patch("atlassian_local_cli.wiki.get_config")
    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_frontmatter(self, mock_create, mock_config, capsys):
        mock_config.return_value = MagicMock(wiki_url="https://wiki.test.com/")
        mock_confluence = MagicMock()
        mock_confluence.get_page_by_id.return_value = MOCK_PAGE
        mock_create.return_value = mock_confluence

        wiki_export(Namespace(page_id="12345", output=None))
        output = capsys.readouterr().out
        assert 'page_id: "12345"' in output
        assert "space: DEV" in output
        assert "version: 3" in output
        assert "author: Test Author" in output


class TestWikiUpdate:
    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_reads_file_and_updates(self, mock_create, tmp_path):
        mock_confluence = MagicMock()
        mock_confluence.get_page_by_id.return_value = {"title": "Old Title", "version": {"number": 2}}
        mock_create.return_value = mock_confluence

        md_file = tmp_path / "input.md"
        md_file.write_text("# New Title\n\nSome content")

        wiki_update(Namespace(page_id="12345", input_file=str(md_file)))
        mock_confluence.update_page.assert_called_once()
        call_args = mock_confluence.update_page.call_args
        assert call_args[0][0] == "12345"
        assert call_args[0][1] == "New Title"

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_uses_page_title_fallback(self, mock_create, tmp_path):
        mock_confluence = MagicMock()
        mock_confluence.get_page_by_id.return_value = {"title": "Existing Title", "version": {"number": 2}}
        mock_create.return_value = mock_confluence

        md_file = tmp_path / "input.md"
        md_file.write_text("No heading here, just content.")

        wiki_update(Namespace(page_id="12345", input_file=str(md_file)))
        call_args = mock_confluence.update_page.call_args
        assert call_args[0][1] == "Existing Title"


class TestWikiCreate:
    @patch("atlassian_local_cli.wiki.get_config")
    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_creates_page(self, mock_create, mock_config, tmp_path, capsys):
        mock_config.return_value = MagicMock(wiki_url="https://wiki.test.com/")
        mock_confluence = MagicMock()
        mock_confluence.create_page.return_value = {"id": "99999"}
        mock_create.return_value = mock_confluence

        md_file = tmp_path / "input.md"
        md_file.write_text("# Ignored Title\n\nPage content here")

        wiki_create(Namespace(space="DEV", title="My New Page", input_file=str(md_file), parent=None))
        mock_confluence.create_page.assert_called_once()
        kwargs = mock_confluence.create_page.call_args[1]
        assert kwargs["space"] == "DEV"
        assert kwargs["title"] == "My New Page"

    @patch("atlassian_local_cli.wiki.get_config")
    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_with_parent(self, mock_create, mock_config, tmp_path, capsys):
        mock_config.return_value = MagicMock(wiki_url="https://wiki.test.com/")
        mock_confluence = MagicMock()
        mock_confluence.create_page.return_value = {"id": "99999"}
        mock_create.return_value = mock_confluence

        md_file = tmp_path / "input.md"
        md_file.write_text("Content")

        wiki_create(Namespace(space="DEV", title="Child", input_file=str(md_file), parent="11111"))
        kwargs = mock_confluence.create_page.call_args[1]
        assert kwargs["parent_id"] == "11111"
