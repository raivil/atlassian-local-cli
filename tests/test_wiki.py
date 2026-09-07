import json
from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from atlassian_local_cli.converters import md_to_confluence_html
from atlassian_local_cli.wiki import (
    wiki_attachments,
    wiki_create,
    wiki_delete,
    wiki_export,
    wiki_raw,
    wiki_update,
)

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
    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_stdout(self, mock_create, capsys):
        mock_confluence = MagicMock()
        mock_confluence.get_page_by_id.return_value = MOCK_PAGE
        mock_create.return_value = mock_confluence

        wiki_export(Namespace(page_id="12345", output=None, attachments=False))
        output = capsys.readouterr().out
        assert "# Test Page" in output
        assert "Hello world" in output

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_to_file(self, mock_create, tmp_path):
        mock_confluence = MagicMock()
        mock_confluence.get_page_by_id.return_value = MOCK_PAGE
        mock_create.return_value = mock_confluence

        outfile = str(tmp_path / "out.md")
        wiki_export(Namespace(page_id="12345", output=outfile, attachments=False))
        content = (tmp_path / "out.md").read_text()
        assert "# Test Page" in content

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_frontmatter(self, mock_create, capsys):
        mock_confluence = MagicMock()
        mock_confluence.get_page_by_id.return_value = MOCK_PAGE
        mock_create.return_value = mock_confluence

        wiki_export(Namespace(page_id="12345", output=None, attachments=False))
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

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_export_then_update_preserves_table_verbatim(
        self, mock_create, tmp_path
    ):
        mock_confluence = MagicMock()
        mock_confluence.get_page_by_id.return_value = self._page()
        mock_create.return_value = mock_confluence

        outfile = str(tmp_path / "out.md")
        wiki_export(Namespace(page_id="12345", output=outfile, attachments=False))
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

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_long_cell_stays_on_one_line(self, mock_create, tmp_path):
        mock_confluence = MagicMock()
        mock_confluence.get_page_by_id.return_value = self._page()
        mock_create.return_value = mock_confluence

        outfile = str(tmp_path / "out.md")
        wiki_export(Namespace(page_id="12345", output=outfile, attachments=False))
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
    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_creates_page(self, mock_create, tmp_path, capsys):
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

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_with_parent(self, mock_create, tmp_path, capsys):
        mock_confluence = MagicMock()
        mock_confluence.create_page.return_value = {"id": "99999"}
        mock_create.return_value = mock_confluence

        md_file = tmp_path / "input.md"
        md_file.write_text("Content")

        wiki_create(Namespace(space="DEV", title="Child", input_file=str(md_file), parent="11111"))
        kwargs = mock_confluence.create_page.call_args[1]
        assert kwargs["parent_id"] == "11111"


def _attachment(title, size=1024, media_type="text/plain", att_id="att1", version=1,
                when="2026-09-04T10:10:21.457Z", download=None):
    return {
        "id": att_id,
        "title": title,
        "version": {"number": version, "when": when},
        "extensions": {"mediaType": media_type, "fileSize": size},
        "_links": {"download": download or f"/download/attachments/12345/{title}?version={version}"},
    }


def _page(results, limit=50):
    return {"start": 0, "limit": limit, "size": len(results), "results": results}


class TestWikiAttachmentsList:
    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_lists_name_size_and_totals(self, mock_create, capsys):
        mock_confluence = MagicMock()
        mock_confluence.get_attachments_from_content.return_value = _page([
            _attachment("query1.txt", size=4119),
            _attachment("pgdiag.sql", size=17061, media_type="application/octet-stream"),
        ])
        mock_create.return_value = mock_confluence

        wiki_attachments(Namespace(page_id="12345", output=None, match=None, json=False))

        out = capsys.readouterr().out
        assert "query1.txt" in out
        assert "4.0 KB" in out
        assert "pgdiag.sql" in out
        assert "16.7 KB" in out
        assert "application/octet-stream" in out
        assert "2026-09-04" in out
        assert "2 attachments, 20.7 KB total" in out

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_json_output(self, mock_create, capsys):
        mock_confluence = MagicMock()
        mock_confluence.get_attachments_from_content.return_value = _page([
            _attachment("query1.txt", size=4119, att_id="att99", version=3),
        ])
        mock_create.return_value = mock_confluence

        wiki_attachments(Namespace(page_id="12345", output=None, match=None, json=True))

        data = json.loads(capsys.readouterr().out)
        assert data == [{
            "id": "att99",
            "title": "query1.txt",
            "media_type": "text/plain",
            "size": 4119,
            "version": 3,
            "updated": "2026-09-04T10:10:21.457Z",
            "download_url": "/download/attachments/12345/query1.txt?version=3",
        }]

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_paginates_past_the_first_page(self, mock_create, capsys):
        first = _page([_attachment(f"f{i}.txt") for i in range(50)])
        second = _page([_attachment(f"g{i}.txt") for i in range(3)])
        mock_confluence = MagicMock()
        mock_confluence.get_attachments_from_content.side_effect = [first, second]
        mock_create.return_value = mock_confluence

        wiki_attachments(Namespace(page_id="12345", output=None, match=None, json=False))

        assert "53 attachments" in capsys.readouterr().out
        starts = [c.kwargs["start"] for c in mock_confluence.get_attachments_from_content.call_args_list]
        assert starts == [0, 50]

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_match_filters_by_glob(self, mock_create, capsys):
        mock_confluence = MagicMock()
        mock_confluence.get_attachments_from_content.return_value = _page([
            _attachment("query1.txt"), _attachment("query2.txt"), _attachment("pgdiag.sql"),
        ])
        mock_create.return_value = mock_confluence

        wiki_attachments(Namespace(page_id="12345", output=None, match="query*.txt", json=False))

        out = capsys.readouterr().out
        assert "query1.txt" in out
        assert "pgdiag.sql" not in out
        assert "2 attachments" in out

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_reports_empty_page(self, mock_create, capsys):
        mock_confluence = MagicMock()
        mock_confluence.get_attachments_from_content.return_value = _page([])
        mock_create.return_value = mock_confluence

        wiki_attachments(Namespace(page_id="12345", output=None, match=None, json=False))

        assert "No attachments on page 12345." in capsys.readouterr().out


class TestWikiAttachmentsDownload:
    @staticmethod
    def _client(results, bodies):
        confluence = MagicMock()
        confluence.get_attachments_from_content.return_value = _page(results)
        confluence.get.side_effect = lambda url, **kwargs: bodies[url]
        return confluence

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_downloads_into_directory(self, mock_create, tmp_path, capsys):
        mock_create.return_value = self._client(
            [_attachment("query1.txt"), _attachment("pgdiag.sql")],
            {
                "/download/attachments/12345/query1.txt?version=1": b"hello",
                "/download/attachments/12345/pgdiag.sql?version=1": b"sql",
            },
        )

        target = tmp_path / "att"
        wiki_attachments(Namespace(page_id="12345", output=str(target), match=None, json=False))

        assert (target / "query1.txt").read_bytes() == b"hello"
        assert (target / "pgdiag.sql").read_bytes() == b"sql"
        assert mock_create.return_value.get.call_args_list[0].kwargs["not_json_response"] is True
        out = capsys.readouterr().out
        assert "Downloaded query1.txt (5 B)" in out
        assert f"2 attachments -> {target}" in out

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_strips_path_traversal_from_title(self, mock_create, tmp_path):
        mock_create.return_value = self._client(
            [_attachment("../../../evil.txt", download="/dl/evil")], {"/dl/evil": b"pwned"}
        )

        target = tmp_path / "att"
        wiki_attachments(Namespace(page_id="12345", output=str(target), match=None, json=False))

        assert (target / "evil.txt").read_bytes() == b"pwned"
        assert list(target.iterdir()) == [target / "evil.txt"]

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_dedupes_names_colliding_after_sanitizing(self, mock_create, tmp_path):
        mock_create.return_value = self._client(
            [_attachment("a/x.txt", download="/dl/1"), _attachment("b/x.txt", download="/dl/2")],
            {"/dl/1": b"first", "/dl/2": b"second"},
        )

        target = tmp_path / "att"
        wiki_attachments(Namespace(page_id="12345", output=str(target), match=None, json=False))

        assert (target / "x.txt").read_bytes() == b"first"
        assert (target / "x (1).txt").read_bytes() == b"second"

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_skips_names_resolving_outside_target(self, mock_create, tmp_path, capsys):
        outside = tmp_path / "outside"
        outside.mkdir()
        target = tmp_path / "att"
        target.mkdir()
        (target / "x.txt").symlink_to(outside / "x.txt")
        mock_create.return_value = self._client(
            [_attachment("x.txt", download="/dl/x")], {"/dl/x": b"escaped"}
        )

        wiki_attachments(Namespace(page_id="12345", output=str(target), match=None, json=False))

        assert not (outside / "x.txt").exists()
        assert "x.txt" in capsys.readouterr().err

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_download_respects_match(self, mock_create, tmp_path):
        mock_create.return_value = self._client(
            [_attachment("query1.txt"), _attachment("pgdiag.sql")],
            {"/download/attachments/12345/query1.txt?version=1": b"hello"},
        )

        target = tmp_path / "att"
        wiki_attachments(Namespace(page_id="12345", output=str(target), match="*.txt", json=False))

        assert [p.name for p in target.iterdir()] == ["query1.txt"]

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_reports_when_match_finds_nothing(self, mock_create, capsys):
        mock_create.return_value = self._client([_attachment("query1.txt")], {})

        wiki_attachments(Namespace(page_id="12345", output=None, match="*.pdf", json=False))

        assert "No attachments matching '*.pdf' on page 12345." in capsys.readouterr().out


class TestPageUrlBase:
    """Cloud serves Confluence under /wiki, which the client appends but
    config.wiki_url never carries — so page URLs must come from the client."""

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_export_frontmatter_url_uses_client_base(self, mock_create, capsys):
        confluence = MagicMock()
        confluence.url = "https://valr-br.atlassian.net/wiki"
        confluence.get_page_by_id.return_value = MOCK_PAGE
        mock_create.return_value = confluence

        wiki_export(Namespace(page_id="12345", output=None, attachments=False))

        assert "url: https://valr-br.atlassian.net/wiki/pages/viewpage.action?pageId=12345" in capsys.readouterr().out

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_export_frontmatter_url_unchanged_on_server(self, mock_create, capsys):
        confluence = MagicMock()
        confluence.url = "https://wiki.test.com/"
        confluence.get_page_by_id.return_value = MOCK_PAGE
        mock_create.return_value = confluence

        wiki_export(Namespace(page_id="12345", output=None, attachments=False))

        assert "url: https://wiki.test.com/pages/viewpage.action?pageId=12345" in capsys.readouterr().out

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_create_prints_url_from_client_base(self, mock_create, tmp_path, capsys):
        confluence = MagicMock()
        confluence.url = "https://valr-br.atlassian.net/wiki"
        confluence.create_page.return_value = {"id": "99999"}
        mock_create.return_value = confluence

        md_file = tmp_path / "in.md"
        md_file.write_text("# T\n\nbody")
        wiki_create(Namespace(space="DEV", title="T", input_file=str(md_file), parent=None))

        assert "https://valr-br.atlassian.net/wiki/pages/viewpage.action?pageId=99999" in capsys.readouterr().out


IMAGE_PAGE = {
    **MOCK_PAGE,
    "body": {
        "export_view": {"value": '<p><img src="https://wiki.test.com/download/attachments/12345/pic.png?api=v2" alt="sq" /></p>'},
        "storage": {"value": '<p><ac:image ac:alt="sq"><ri:attachment ri:filename="pic.png" /></ac:image></p>'},
    },
}


class TestWikiExportAttachments:
    @staticmethod
    def _client(attachments, bodies):
        confluence = MagicMock()
        confluence.url = "https://wiki.test.com/"
        confluence.get_page_by_id.return_value = IMAGE_PAGE
        confluence.get_attachments_from_content.return_value = _page(attachments)
        confluence.get.side_effect = lambda url, **kwargs: bodies[url]
        return confluence

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_requires_output_directory(self, mock_create, capsys):
        mock_create.return_value = self._client([], {})

        with pytest.raises(SystemExit):
            wiki_export(Namespace(page_id="12345", output=None, attachments=True))

        assert "--attachments" in capsys.readouterr().err

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_rewrites_links_and_downloads_only_referenced_files(self, mock_create, tmp_path):
        mock_create.return_value = self._client(
            [_attachment("pic.png", download="/dl/pic"), _attachment("unrelated.txt", download="/dl/txt")],
            {"/dl/pic": b"PNGDATA"},
        )

        out = tmp_path / "page.md"
        wiki_export(Namespace(page_id="12345", output=str(out), attachments=True))

        assert "![sq](pic.png)" in out.read_text()
        assert (tmp_path / "pic.png").read_bytes() == b"PNGDATA"
        assert not (tmp_path / "unrelated.txt").exists()

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_without_the_flag_links_stay_absolute(self, mock_create, tmp_path):
        confluence = self._client([], {})
        mock_create.return_value = confluence

        out = tmp_path / "page.md"
        wiki_export(Namespace(page_id="12345", output=str(out), attachments=False))

        assert "https://wiki.test.com/download/attachments/12345/pic.png" in out.read_text()
        confluence.get_attachments_from_content.assert_not_called()

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_reports_referenced_files_that_are_not_attachments(self, mock_create, tmp_path, capsys):
        mock_create.return_value = self._client([], {})

        out = tmp_path / "page.md"
        wiki_export(Namespace(page_id="12345", output=str(out), attachments=True))

        assert "pic.png" in capsys.readouterr().err


class TestWikiUpdateMissingImages:
    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_warns_when_a_local_image_has_no_file(self, mock_create, tmp_path, capsys):
        confluence = MagicMock()
        confluence.get_page_by_id.return_value = {"title": "P", "version": {"number": 1}}
        mock_create.return_value = confluence

        md = tmp_path / "in.md"
        md.write_text("# T\n\n![x](missing.png)\n")
        wiki_update(Namespace(page_id="12345", input_file=str(md)))

        err = capsys.readouterr().err
        assert "missing.png" in err
        confluence.update_page.assert_called_once()

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_does_not_warn_for_external_images(self, mock_create, tmp_path, capsys):
        confluence = MagicMock()
        confluence.get_page_by_id.return_value = {"title": "P", "version": {"number": 1}}
        mock_create.return_value = confluence

        md = tmp_path / "in.md"
        md.write_text("# T\n\n![x](https://example.com/logo.png)\n")
        wiki_update(Namespace(page_id="12345", input_file=str(md)))

        assert capsys.readouterr().err == ""

    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_create_warns_too(self, mock_create, tmp_path, capsys):
        confluence = MagicMock()
        confluence.url = "https://wiki.test.com/"
        confluence.create_page.return_value = {"id": "999"}
        mock_create.return_value = confluence

        md = tmp_path / "in.md"
        md.write_text("# T\n\n![x](gone.png)\n")
        wiki_create(Namespace(space="DEV", title="T", input_file=str(md), parent=None))

        assert "gone.png" in capsys.readouterr().err


class TestWikiRawFormat:
    @patch("atlassian_local_cli.wiki.create_confluence")
    def test_format_export_returns_the_rendered_body(self, mock_create, capsys):
        confluence = MagicMock()
        confluence.get_page_by_id.return_value = MOCK_PAGE
        mock_create.return_value = confluence

        wiki_raw(Namespace(page_id="12345", format="export", macros=False, output=None))

        out = capsys.readouterr().out
        assert "export_view" in out
        assert "Hello world" in out
