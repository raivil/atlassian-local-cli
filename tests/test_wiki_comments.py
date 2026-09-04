import json
from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from atlassian_local_cli.wiki_comments import (
    wiki_comment,
    wiki_comment_delete,
    wiki_comments,
)


def _comment(body="<p>Hello</p>", author="Marco Carvalho", cid="9001", ancestors=(),
             created="2026-09-04T10:15:00.000Z", location="footer"):
    return {
        "id": cid,
        "type": "comment",
        "ancestors": [{"id": a} for a in ancestors],
        "history": {"createdBy": {"displayName": author}, "createdDate": created},
        "version": {"number": 1, "when": created},
        "body": {"storage": {"value": body, "representation": "storage"}},
        "extensions": {"location": location},
    }


def _page(results, limit=50):
    return {"start": 0, "limit": limit, "size": len(results), "results": list(results)}


class TestWikiCommentsList:
    @patch("atlassian_local_cli.wiki_comments.create_confluence")
    def test_prints_author_timestamp_id_and_body(self, mock_create, capsys):
        confluence = MagicMock()
        confluence.get_page_comments.return_value = _page([_comment()])
        mock_create.return_value = confluence

        wiki_comments(Namespace(page_id="12345", location="all", json=False))

        out = capsys.readouterr().out
        assert "--- Marco Carvalho @ 2026-09-04T10:15:00.000Z (id: 9001) ---" in out
        assert "Hello" in out

    @patch("atlassian_local_cli.wiki_comments.create_confluence")
    def test_converts_storage_html_to_markdown(self, mock_create, capsys):
        confluence = MagicMock()
        confluence.get_page_comments.return_value = _page([
            _comment(body="<p>Saw <strong>98% CPU</strong></p><ul><li>lag climbing</li></ul>"),
        ])
        mock_create.return_value = confluence

        wiki_comments(Namespace(page_id="12345", location="all", json=False))

        out = capsys.readouterr().out
        assert "**98% CPU**" in out
        assert "lag climbing" in out
        assert "<strong>" not in out
        assert "<ul>" not in out

    @patch("atlassian_local_cli.wiki_comments.create_confluence")
    def test_indents_replies_by_ancestor_depth(self, mock_create, capsys):
        confluence = MagicMock()
        confluence.get_page_comments.return_value = _page([
            _comment(body="<p>root</p>", cid="1"),
            _comment(body="<p>reply</p>", cid="2", ancestors=("1",)),
        ])
        mock_create.return_value = confluence

        wiki_comments(Namespace(page_id="12345", location="all", json=False))

        lines = capsys.readouterr().out.splitlines()
        assert any(line.startswith("--- Marco") for line in lines)
        assert any(line.startswith("  --- Marco") and "id: 2" in line for line in lines)
        assert any(line.startswith("  reply") for line in lines)

    @patch("atlassian_local_cli.wiki_comments.create_confluence")
    def test_requests_all_locations_and_full_depth_by_default(self, mock_create):
        confluence = MagicMock()
        confluence.get_page_comments.return_value = _page([])
        mock_create.return_value = confluence

        wiki_comments(Namespace(page_id="12345", location="all", json=False))

        kwargs = confluence.get_page_comments.call_args.kwargs
        assert kwargs["content_id"] == "12345"
        assert kwargs["depth"] == "all"
        assert kwargs["location"] is None
        assert "body.storage" in kwargs["expand"]
        assert "ancestors" in kwargs["expand"]

    @patch("atlassian_local_cli.wiki_comments.create_confluence")
    def test_passes_location_filter_through(self, mock_create):
        confluence = MagicMock()
        confluence.get_page_comments.return_value = _page([])
        mock_create.return_value = confluence

        wiki_comments(Namespace(page_id="12345", location="resolved", json=False))

        assert confluence.get_page_comments.call_args.kwargs["location"] == "resolved"

    @patch("atlassian_local_cli.wiki_comments.create_confluence")
    def test_pages_past_the_first_response(self, mock_create, capsys):
        confluence = MagicMock()
        confluence.get_page_comments.side_effect = [
            _page([_comment(cid=str(i)) for i in range(50)]),
            _page([_comment(cid="x")]),
        ]
        mock_create.return_value = confluence

        wiki_comments(Namespace(page_id="12345", location="all", json=False))

        starts = [c.kwargs["start"] for c in confluence.get_page_comments.call_args_list]
        assert starts == [0, 50]
        assert capsys.readouterr().out.count("--- Marco") == 51

    @patch("atlassian_local_cli.wiki_comments.create_confluence")
    def test_json_emits_raw_payloads(self, mock_create, capsys):
        confluence = MagicMock()
        confluence.get_page_comments.return_value = _page([_comment()])
        mock_create.return_value = confluence

        wiki_comments(Namespace(page_id="12345", location="all", json=True))

        data = json.loads(capsys.readouterr().out)
        assert data[0]["id"] == "9001"
        assert data[0]["body"]["storage"]["value"] == "<p>Hello</p>"

    @patch("atlassian_local_cli.wiki_comments.create_confluence")
    def test_reports_empty_page(self, mock_create, capsys):
        confluence = MagicMock()
        confluence.get_page_comments.return_value = _page([])
        mock_create.return_value = confluence

        wiki_comments(Namespace(page_id="12345", location="all", json=False))

        assert "No comments on page 12345." in capsys.readouterr().out


class TestWikiCommentAdd:
    @patch("atlassian_local_cli.wiki_comments.create_confluence")
    def test_converts_markdown_body_to_storage_format(self, mock_create):
        confluence = MagicMock()
        confluence.add_comment.return_value = {"id": "555"}
        mock_create.return_value = confluence

        wiki_comment(Namespace(page_id="12345", body="Saw **98% CPU**\n\n- lag climbing\n", body_file=None))

        posted = confluence.add_comment.call_args[0][1]
        assert "<strong>98% CPU</strong>" in posted
        assert "<li>lag climbing</li>" in posted
        assert "**" not in posted
        assert confluence.add_comment.call_args[0][0] == "12345"

    @patch("atlassian_local_cli.wiki_comments.create_confluence")
    def test_reads_body_from_file(self, mock_create, tmp_path):
        confluence = MagicMock()
        confluence.add_comment.return_value = {"id": "556"}
        mock_create.return_value = confluence
        f = tmp_path / "note.md"
        f.write_text("plain note\n")

        wiki_comment(Namespace(page_id="12345", body=None, body_file=str(f)))

        assert "plain note" in confluence.add_comment.call_args[0][1]

    @patch("atlassian_local_cli.wiki_comments.create_confluence")
    def test_prints_new_comment_id(self, mock_create, capsys):
        confluence = MagicMock()
        confluence.add_comment.return_value = {"id": "557"}
        mock_create.return_value = confluence

        wiki_comment(Namespace(page_id="12345", body="hi", body_file=None))

        assert "Comment added to page 12345 (id: 557)" in capsys.readouterr().out

    @patch("atlassian_local_cli.wiki_comments.create_confluence")
    def test_requires_a_body(self, mock_create, capsys):
        mock_create.return_value = MagicMock()

        with pytest.raises(SystemExit):
            wiki_comment(Namespace(page_id="12345", body=None, body_file=None))

        assert "body is required" in capsys.readouterr().err


class TestWikiCommentDelete:
    @patch("atlassian_local_cli.wiki_comments.create_confluence")
    def test_requires_yes(self, mock_create):
        confluence = MagicMock()
        mock_create.return_value = confluence

        with pytest.raises(SystemExit):
            wiki_comment_delete(Namespace(comment_id="9001", yes=False))

        confluence.remove_content.assert_not_called()

    @patch("atlassian_local_cli.wiki_comments.create_confluence")
    def test_deletes_a_comment(self, mock_create, capsys):
        confluence = MagicMock()
        confluence.get_page_by_id.return_value = {"id": "9001", "type": "comment"}
        mock_create.return_value = confluence

        wiki_comment_delete(Namespace(comment_id="9001", yes=True))

        confluence.remove_content.assert_called_once_with("9001")
        assert "Deleted comment 9001" in capsys.readouterr().out

    @patch("atlassian_local_cli.wiki_comments.create_confluence")
    def test_refuses_a_page_id(self, mock_create, capsys):
        confluence = MagicMock()
        confluence.get_page_by_id.return_value = {"id": "990019585", "type": "page"}
        mock_create.return_value = confluence

        with pytest.raises(SystemExit):
            wiki_comment_delete(Namespace(comment_id="990019585", yes=True))

        confluence.remove_content.assert_not_called()
        err = capsys.readouterr().err
        assert "not 'comment'" in err
        assert "page" in err


CODE_MACRO_STORAGE = (
    "<p>Run this:</p>"
    '<ac:structured-macro ac:name="code"><ac:parameter ac:name="language">sql</ac:parameter>'
    "<ac:plain-text-body><![CDATA[select 1 from pg_stat_activity;\n]]></ac:plain-text-body>"
    "</ac:structured-macro>"
)
CODE_MACRO_RENDERED = (
    "<p>Run this:</p>"
    '<div class="code panel pdl"><div class="codeContent panelContent pdl">'
    '<pre class="syntaxhighlighter-pre">select 1 from pg_stat_activity;\n</pre>'
    "</div></div>"
)


class TestWikiCommentsBodyRepresentation:
    @patch("atlassian_local_cli.wiki_comments.create_confluence")
    def test_renders_code_macros_from_the_rendered_body(self, mock_create, capsys):
        comment = _comment(body=CODE_MACRO_STORAGE)
        comment["body"]["export_view"] = {"value": CODE_MACRO_RENDERED}
        confluence = MagicMock()
        confluence.get_page_comments.return_value = _page([comment])
        mock_create.return_value = confluence

        wiki_comments(Namespace(page_id="12345", location="all", json=False))

        out = capsys.readouterr().out
        assert "select 1 from pg_stat_activity;" in out
        assert "ac:plain-text-body" not in out

    @patch("atlassian_local_cli.wiki_comments.create_confluence")
    def test_requests_both_rendered_and_storage_bodies(self, mock_create):
        confluence = MagicMock()
        confluence.get_page_comments.return_value = _page([])
        mock_create.return_value = confluence

        wiki_comments(Namespace(page_id="12345", location="all", json=False))

        expand = confluence.get_page_comments.call_args.kwargs["expand"]
        assert "body.export_view" in expand
        assert "body.storage" in expand

    @patch("atlassian_local_cli.wiki_comments.create_confluence")
    def test_falls_back_to_storage_when_no_rendered_body(self, mock_create, capsys):
        confluence = MagicMock()
        confluence.get_page_comments.return_value = _page([_comment(body="<p>only storage</p>")])
        mock_create.return_value = confluence

        wiki_comments(Namespace(page_id="12345", location="all", json=False))

        assert "only storage" in capsys.readouterr().out
