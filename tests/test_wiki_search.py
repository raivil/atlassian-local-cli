import json
from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest
from atlassian.errors import ApiValueError
from requests import HTTPError

from atlassian_local_cli.wiki_search import build_search_cql, wiki_search

BASE = "https://wiki.test.com"


def _args(**overrides):
    defaults = dict(
        cql=None, text=None, title=None, space=None, type=None, contributor=None,
        modified_since=None, parent=None, order_by=None, reverse=False, limit=25, json=False,
    )
    defaults.update(overrides)
    return Namespace(**defaults)


# Mirrors a live /rest/api/search hit with expand=content.space (Server 2026-11).
def _page_hit(cid="1025966082", title="Week of 2026-11-09", space="HG",
              excerpt="Nov 9 &amp; 13 \u00b7 Infra\n\nreviewed at end of @@@hl@@@week@@@endhl@@@."):
    return {
        "content": {
            "id": cid,
            "type": "page",
            "status": "current",
            "title": title,
            "space": {"key": space, "name": "Agile Team", "type": "global"},
            "position": 0,
            "restrictions": {},
            "_links": {"webui": f"/spaces/{space}/pages/{cid}/X", "tinyui": "/x/AgAnPQ",
                       "self": f"{BASE}/rest/api/content/{cid}"},
            "_expandable": {"history": f"/rest/api/content/{cid}/history"},
        },
        "title": title.replace("Week", "@@@hl@@@Week@@@endhl@@@"),
        "excerpt": excerpt,
        "url": f"/spaces/{space}/pages/{cid}/Week+of+2026-11-09",
        "resultGlobalContainer": {"title": "Agile Team", "displayUrl": f"/spaces/{space}/overview"},
        "entityType": "content",
        "iconCssClass": "aui-icon content-type-page",
        "lastModified": "2026-11-13T16:59:38.409Z",
        "friendlyLastModified": "about 2 hours ago",
        "timestamp": 1794589178409,
    }


def _space_hit(key="HG", name="Agile Team - Henry Gray"):
    return {
        "space": {"key": key, "name": name, "type": "global", "metadata": {},
                  "_links": {"self": f"{BASE}/rest/api/space/{key}"}},
        "title": name,
        "excerpt": "",
        "url": f"/display/{key}",
        "resultGlobalContainer": {"title": name, "displayUrl": f"/spaces/{key}/overview"},
        "entityType": "space",
        "iconCssClass": "aui-icon content-type-space",
        "lastModified": "2019-09-28T11:13:04.870Z",
        "friendlyLastModified": "Sep 28, 2019",
        "timestamp": 1569669184870,
    }


class FakeConfluence:
    """Serves `hits` the way /rest/api/search does: honours start/limit, reports
    totalSize, and optionally caps a page below the requested limit."""

    def __init__(self, hits, cap=None):
        self.hits = hits
        self.cap = cap
        self.url = BASE + "/"
        self.calls = []

    def cql(self, cql, start=0, limit=None, expand=None, include_archived_spaces=None, excerpt=None):
        self.calls.append({"cql": cql, "start": start, "limit": limit, "expand": expand})
        size = limit if self.cap is None else min(limit, self.cap)
        batch = self.hits[start:start + size]
        return {"results": batch, "start": start, "limit": size, "size": len(batch),
                "totalSize": len(self.hits), "cqlQuery": cql, "_links": {"base": BASE, "context": ""}}


class TestBuildSearchCql:
    def test_filters_are_and_combined(self):
        cql = build_search_cql(_args(text="pentest", space="HG", type="page"))
        assert cql == 'text ~ "pentest" AND space = "HG" AND type = page'

    def test_contributor_me_is_the_current_user(self):
        assert build_search_cql(_args(contributor="me")) == "contributor = currentUser()"

    def test_named_contributor_is_quoted(self):
        assert build_search_cql(_args(contributor="rraivil")) == 'contributor = "rraivil"'

    def test_title_parent_and_modified_since(self):
        cql = build_search_cql(_args(title="Week of", parent="982417416", modified_since="2026-11-01"))
        assert cql == 'title ~ "Week of" AND parent = "982417416" AND lastmodified >= "2026-11-01"'

    def test_quotes_and_backslashes_in_values_are_escaped(self):
        cql = build_search_cql(_args(title='say "hi" C:\\temp'))
        assert cql == 'title ~ "say \\"hi\\" C:\\\\temp"'

    def test_raw_cql_alone_is_sent_unwrapped(self):
        assert build_search_cql(_args(cql="label = runbook")) == "label = runbook"

    def test_raw_cql_is_parenthesised_when_filters_join_it(self):
        cql = build_search_cql(_args(cql="label = a OR label = b", space="HG"))
        assert cql == '(label = a OR label = b) AND space = "HG"'

    def test_order_by_in_raw_cql_moves_after_the_filters(self):
        cql = build_search_cql(_args(cql="contributor = currentUser() order by lastmodified desc", space="HG"))
        assert cql == '(contributor = currentUser()) AND space = "HG" order by lastmodified desc'

    def test_order_by_inside_a_quoted_string_is_not_a_clause(self):
        cql = build_search_cql(_args(cql='text ~ "sort order by date"', space="HG"))
        assert cql == '(text ~ "sort order by date") AND space = "HG"'

    def test_order_by_flag_defaults_to_descending(self):
        assert build_search_cql(_args(space="HG", order_by="lastmodified")) == 'space = "HG" order by lastmodified desc'

    def test_reverse_orders_ascending(self):
        cql = build_search_cql(_args(space="HG", order_by="created", reverse=True))
        assert cql == 'space = "HG" order by created asc'

    def test_order_by_flag_and_raw_order_by_conflict(self):
        with pytest.raises(ValueError):
            build_search_cql(_args(cql="type = page order by title", order_by="created"))

    def test_nothing_to_search_for_yields_empty(self):
        assert build_search_cql(_args()) == ""
        assert build_search_cql(_args(order_by="created")) == ""


class TestPaging:
    @patch("atlassian_local_cli.wiki_search.create_confluence")
    def test_keeps_paging_when_the_server_caps_a_page(self, mock_create, capsys):
        hits = [_page_hit(cid=str(i)) for i in range(7)]
        fake = FakeConfluence(hits, cap=3)
        mock_create.return_value = fake

        wiki_search(_args(space="HG", limit=5, json=True))

        rows = json.loads(capsys.readouterr().out)
        assert [r["id"] for r in rows] == ["0", "1", "2", "3", "4"]
        assert [(c["start"], c["limit"]) for c in fake.calls] == [(0, 5), (3, 2)]

    @patch("atlassian_local_cli.wiki_search.create_confluence")
    def test_stops_at_total_size_without_an_extra_request(self, mock_create, capsys):
        fake = FakeConfluence([_page_hit(cid=str(i)) for i in range(4)], cap=2)
        mock_create.return_value = fake

        wiki_search(_args(space="HG", limit=25, json=True))

        assert len(json.loads(capsys.readouterr().out)) == 4
        assert [c["start"] for c in fake.calls] == [0, 2]

    @patch("atlassian_local_cli.wiki_search.create_confluence")
    def test_stops_on_an_empty_page_even_if_total_claims_more(self, mock_create, capsys):
        confluence = MagicMock()
        confluence.url = BASE + "/"
        confluence.cql.side_effect = [
            {"results": [_page_hit(cid="1")], "start": 0, "limit": 25, "size": 1, "totalSize": 9},
            {"results": [], "start": 1, "limit": 24, "size": 0, "totalSize": 9},
        ]
        mock_create.return_value = confluence

        wiki_search(_args(space="HG", json=True))

        assert [r["id"] for r in json.loads(capsys.readouterr().out)] == ["1"]
        assert confluence.cql.call_count == 2

    @patch("atlassian_local_cli.wiki_search.create_confluence")
    def test_expands_the_space_so_rows_carry_its_key(self, mock_create, capsys):
        fake = FakeConfluence([_page_hit()])
        mock_create.return_value = fake

        wiki_search(_args(space="HG", json=True))

        assert "content.space" in fake.calls[0]["expand"]


class TestOutput:
    @patch("atlassian_local_cli.wiki_search.create_confluence")
    def test_json_row_for_a_page(self, mock_create, capsys):
        mock_create.return_value = FakeConfluence([_page_hit()])

        wiki_search(_args(text="week", json=True))

        assert json.loads(capsys.readouterr().out) == [{
            "id": "1025966082",
            "type": "page",
            "title": "Week of 2026-11-09",
            "space": "HG",
            "url": "https://wiki.test.com/spaces/HG/pages/1025966082/Week+of+2026-11-09",
            "last_modified": "2026-11-13T16:59:38.409Z",
            "excerpt": "Nov 9 & 13 \u00b7 Infra reviewed at end of week.",
        }]

    @patch("atlassian_local_cli.wiki_search.create_confluence")
    def test_space_hits_have_no_content_id(self, mock_create, capsys):
        mock_create.return_value = FakeConfluence([_space_hit()])

        wiki_search(_args(text="agile", json=True))

        row = json.loads(capsys.readouterr().out)[0]
        assert row["id"] is None
        assert row["type"] == "space"
        assert row["space"] == "HG"
        assert row["title"] == "Agile Team - Henry Gray"
        assert row["url"] == "https://wiki.test.com/display/HG"

    @patch("atlassian_local_cli.wiki_search.create_confluence")
    def test_text_output_lists_id_space_title_and_excerpt(self, mock_create, capsys):
        mock_create.return_value = FakeConfluence([_page_hit(), _space_hit()])

        wiki_search(_args(text="week"))

        out = capsys.readouterr().out
        page_line = next(line for line in out.splitlines() if "1025966082" in line)
        assert "HG" in page_line and "2026-11-13" in page_line and "Week of 2026-11-09" in page_line
        assert "reviewed at end of week." in out
        assert "@@@hl@@@" not in out

    @patch("atlassian_local_cli.wiki_search.create_confluence")
    def test_columns_align_when_values_are_narrower_than_headers(self, mock_create, capsys):
        mock_create.return_value = FakeConfluence([_page_hit(cid="7", space="HG")])

        wiki_search(_args(text="week"))

        header, _, row = capsys.readouterr().out.splitlines()[:3]
        assert row.index("2026-11-13") == header.index("Modified")
        assert row.index("Week of") == header.index("Title")

    @patch("atlassian_local_cli.wiki_search.create_confluence")
    def test_truncation_is_reported_on_stderr(self, mock_create, capsys):
        mock_create.return_value = FakeConfluence([_page_hit(cid=str(i)) for i in range(5)])

        wiki_search(_args(space="HG", limit=2, json=True))

        captured = capsys.readouterr()
        assert len(json.loads(captured.out)) == 2
        assert "2 of 5" in captured.err

    @patch("atlassian_local_cli.wiki_search.create_confluence")
    def test_complete_results_say_nothing_on_stderr(self, mock_create, capsys):
        mock_create.return_value = FakeConfluence([_page_hit()])

        wiki_search(_args(space="HG", json=True))

        assert capsys.readouterr().err == ""

    @patch("atlassian_local_cli.wiki_search.create_confluence")
    def test_no_results(self, mock_create, capsys):
        mock_create.return_value = FakeConfluence([])

        wiki_search(_args(space="HG"))

        assert "No results" in capsys.readouterr().out


class TestErrors:
    @patch("atlassian_local_cli.wiki_search.create_confluence")
    def test_no_query_exits_before_building_the_client(self, mock_create, capsys):
        with pytest.raises(SystemExit) as exc:
            wiki_search(_args())
        assert exc.value.code == 1
        mock_create.assert_not_called()

    @patch("atlassian_local_cli.wiki_search.create_confluence")
    def test_limit_below_one_exits_rather_than_reporting_no_results(self, mock_create, capsys):
        with pytest.raises(SystemExit) as exc:
            wiki_search(_args(space="HG", limit=0))
        assert exc.value.code == 1
        assert "No results" not in capsys.readouterr().out
        mock_create.assert_not_called()

    @patch("atlassian_local_cli.wiki_search.create_confluence")
    def test_order_by_conflict_exits_before_building_the_client(self, mock_create, capsys):
        with pytest.raises(SystemExit) as exc:
            wiki_search(_args(cql="type = page order by title", order_by="created"))
        assert exc.value.code == 1
        mock_create.assert_not_called()

    @patch("atlassian_local_cli.wiki_search.create_confluence")
    def test_unparseable_cql_surfaces_the_server_reason_and_the_query(self, mock_create, capsys):
        confluence = MagicMock()
        confluence.cql.side_effect = ApiValueError(
            "The query cannot be parsed",
            reason=HTTPError('Missing closing quote on string ("x) near field title.'),
        )
        mock_create.return_value = confluence

        with pytest.raises(SystemExit) as exc:
            wiki_search(_args(cql='title ~ "x'))

        err = capsys.readouterr().err
        assert exc.value.code == 1
        assert "Missing closing quote" in err
        assert 'title ~ "x' in err
