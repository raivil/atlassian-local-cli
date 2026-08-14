from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from atlassian_local_cli.converters import md_to_confluence_html
from atlassian_local_cli.wiki import wiki_create, wiki_delete, wiki_export, wiki_update

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


class TestWikiExportUnsafeTable:
    """A table with block-content cells must survive export -> update verbatim,
    not get scrambled (the confirmed data-loss bug)."""

    STORAGE_TABLE = (
        "<table><tbody>"
        "<tr><th>Date</th><th>Activity</th><th>Status</th></tr>"
        "<tr><td>Week of May 4</td>"
        "<td><p>Reset staging0</p><h4>4-6 hours</h4></td>"
        "<td></td></tr>"
        "<tr><td>Mon May 11</td><td>Migrate</td>"
        '<td><ac:structured-macro ac:name="status">'
        '<ac:parameter ac:name="colour">Green</ac:parameter>'
        '<ac:parameter ac:name="title">DONE</ac:parameter>'
        "</ac:structured-macro></td></tr>"
        "</tbody></table>"
    )
    EXPORT_TABLE = (
        '<table class="wrapped"><tbody>'
        "<tr><th>Date</th><th>Activity</th><th>Status</th></tr>"
        "<tr><td>Week of May 4</td>"
        "<td><p>Reset staging0</p><h4>4-6 hours</h4></td>"
        "<td></td></tr>"
        "<tr><td>Mon May 11</td><td>Migrate</td>"
        '<td><span class="status-macro aui-lozenge aui-lozenge-success">DONE</span></td></tr>'
        "</tbody></table>"
    )

    def _page(self):
        page = {k: v for k, v in MOCK_PAGE.items() if k != "body"}
        page["body"] = {
            "export_view": {"value": self.EXPORT_TABLE},
            "storage": {"value": self.STORAGE_TABLE},
        }
        return page

    @patch("atlassian_local_cli.wiki.get_config")
    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_export_then_update_preserves_table_verbatim(
        self, mock_create, mock_config, tmp_path
    ):
        mock_config.return_value = MagicMock(wiki_url="https://wiki.test.com/")
        mock_confluence = MagicMock()
        mock_confluence.get_page_by_id.return_value = self._page()
        mock_create.return_value = mock_confluence

        outfile = str(tmp_path / "out.md")
        wiki_export(Namespace(page_id="12345", output=outfile))
        exported_md = (tmp_path / "out.md").read_text()

        # The lossy rendered table must NOT appear as editable markdown; it lives in
        # the passthrough footer instead.
        assert "confluence-passthrough-start" in exported_md
        assert self.STORAGE_TABLE in exported_md

        # Re-import the exported markdown and confirm no corruption.
        html = md_to_confluence_html(exported_md)
        assert html.count("<table") == 1
        assert self.STORAGE_TABLE in html
        after_table = html[html.rindex("</table>") + len("</table>"):]
        assert "<h4>" not in after_table
        assert "Mon May 11" not in after_table


class TestWikiExportLongTableCell:
    """A table cell whose text crosses html2text's default wrap width must not be
    split across multiple physical lines: the wrapped continuation carries no
    marker distinguishing it from a real row boundary, so a long cell would
    otherwise corrupt the table on re-import (the fix: h.body_width = 0)."""

    LONG_CELL = (
        "This is a deliberately long cell value that runs well past the seventy "
        "eight character wrap width html2text applies to paragraphs by default, "
        "which used to force it across several physical lines."
    )
    TABLE = (
        "<table><tbody>"
        "<tr><th>Col A</th><th>Col B</th></tr>"
        f"<tr><td>Row1</td><td>{LONG_CELL}</td></tr>"
        "<tr><td>Row2</td><td>Short</td></tr>"
        "</tbody></table>"
    )

    def _page(self):
        page = {k: v for k, v in MOCK_PAGE.items() if k != "body"}
        page["body"] = {
            "export_view": {"value": self.TABLE},
            "storage": {"value": self.TABLE},
        }
        return page

    @patch("atlassian_local_cli.wiki.get_config")
    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_long_cell_stays_on_one_line(self, mock_create, mock_config, tmp_path):
        mock_config.return_value = MagicMock(wiki_url="https://wiki.test.com/")
        mock_confluence = MagicMock()
        mock_confluence.get_page_by_id.return_value = self._page()
        mock_create.return_value = mock_confluence

        outfile = str(tmp_path / "out.md")
        wiki_export(Namespace(page_id="12345", output=outfile))
        lines = (tmp_path / "out.md").read_text().splitlines()

        row1_lines = [line for line in lines if "Row1" in line]
        assert len(row1_lines) == 1
        assert self.LONG_CELL in row1_lines[0]

        # Row2 must stay a distinct row, not swallowed into Row1's wrapped tail.
        row2_lines = [line for line in lines if "Row2" in line]
        assert len(row2_lines) == 1


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

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_uploads_local_images(self, mock_create, tmp_path):
        mock_confluence = MagicMock()
        mock_confluence.get_page_by_id.return_value = {"title": "Page", "version": {"number": 1}}
        mock_create.return_value = mock_confluence

        (tmp_path / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        md_file = tmp_path / "input.md"
        md_file.write_text("# Title\n\n![alt](pic.png)\n")

        wiki_update(Namespace(page_id="12345", input_file=str(md_file)))

        mock_confluence.attach_file.assert_called_once()
        kwargs = mock_confluence.attach_file.call_args.kwargs
        assert kwargs["page_id"] == "12345"
        assert kwargs["name"] == "pic.png"
        # Body sent to update_page uses ac:image with the attachment filename
        update_body = mock_confluence.update_page.call_args[0][2]
        assert 'ri:filename="pic.png"' in update_body
        assert "<img" not in update_body


class TestWikiDelete:
    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_requires_yes(self, mock_create):
        mock_create.return_value = MagicMock()
        with pytest.raises(SystemExit):
            wiki_delete(Namespace(page_id="12345", yes=False, cascade=False))

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_deletes_with_yes(self, mock_create, capsys):
        mock_confluence = MagicMock()
        mock_confluence.get_page_by_id.return_value = {"title": "Old Page"}
        mock_create.return_value = mock_confluence

        wiki_delete(Namespace(page_id="12345", yes=True, cascade=True))
        mock_confluence.remove_page.assert_called_once_with("12345", recursive=True)
        assert "Deleted page 12345: Old Page" in capsys.readouterr().out


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
