import json
from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from atlassian_local_cli.jira_extras import (
    build_search_jql,
    jira_clone,
    jira_comment,
    jira_comments,
    jira_delete,
    jira_epic_issues,
    jira_epics,
    jira_link,
    jira_link_types,
    jira_me,
    jira_open,
    jira_search,
    jira_sprint_add,
    jira_sprint_issues,
    jira_sprints,
    jira_unlink,
    jira_worklog,
    parse_time_spec,
)


def _search_args(**kw):
    defaults = dict(jql=None, assignee=None, reporter=None, status=None, status_name=None,
                    type=None, priority=None, project=None, label=None, order_by=None,
                    reverse=False, limit=50, json=False, csv=False)
    defaults.update(kw)
    return Namespace(**defaults)


class TestBuildSearchJql:
    def test_raw_jql_default_ordering_skipped(self):
        jql = build_search_jql(_search_args(jql="status = Open"))
        assert jql == "(status = Open)"

    def test_assignee_me(self):
        jql = build_search_jql(_search_args(assignee="me"))
        assert "assignee = currentUser()" in jql
        assert "ORDER BY updated DESC" in jql

    def test_assignee_none(self):
        jql = build_search_jql(_search_args(assignee="none"))
        assert "assignee is EMPTY" in jql

    def test_filters_combined(self):
        jql = build_search_jql(_search_args(status="open", type="Bug", project="PROJ",
                                            priority="High", label=["a", "b"]))
        assert 'statusCategory != "Done"' in jql
        assert 'issuetype = "Bug"' in jql
        assert 'project = "PROJ"' in jql
        assert 'priority = "High"' in jql
        assert 'labels = "a"' in jql
        assert 'labels = "b"' in jql

    def test_order_by_reverse(self):
        jql = build_search_jql(_search_args(project="X", order_by="priority", reverse=True))
        assert jql.endswith("ORDER BY priority ASC")

    def test_jql_and_filters_combine(self):
        jql = build_search_jql(_search_args(jql="text ~ login", assignee="me"))
        assert "(text ~ login)" in jql
        assert "assignee = currentUser()" in jql


class TestJiraMe:
    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_prints_name(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_jira.myself.return_value = {"name": "jdoe", "displayName": "John Doe"}
        mock_create.return_value = mock_jira

        jira_me(Namespace(json=False))
        assert "jdoe" in capsys.readouterr().out

    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_json(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_jira.myself.return_value = {"name": "jdoe"}
        mock_create.return_value = mock_jira

        jira_me(Namespace(json=True))
        assert json.loads(capsys.readouterr().out)["name"] == "jdoe"


class TestJiraOpen:
    @patch("atlassian_local_cli.jira_extras.get_config")
    @patch("atlassian_local_cli.jira_extras.webbrowser.open")
    def test_opens_url(self, mock_open, mock_config, capsys):
        mock_config.return_value = MagicMock(jira_url="https://jira.test/")
        jira_open(Namespace(issue_key="PROJ-1", print_url=False))
        mock_open.assert_called_once_with("https://jira.test/browse/PROJ-1")
        assert "PROJ-1" in capsys.readouterr().out

    @patch("atlassian_local_cli.jira_extras.get_config")
    @patch("atlassian_local_cli.jira_extras.webbrowser.open")
    def test_print_url_only(self, mock_open, mock_config, capsys):
        mock_config.return_value = MagicMock(jira_url="https://jira.test/")
        jira_open(Namespace(issue_key="PROJ-1", print_url=True))
        mock_open.assert_not_called()
        assert capsys.readouterr().out.strip() == "https://jira.test/browse/PROJ-1"


class TestJiraSearch:
    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_no_filters_exits(self, mock_create):
        mock_create.return_value = MagicMock()
        with pytest.raises(SystemExit):
            jira_search(_search_args())

    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_table_output(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_jira.jql.return_value = {"issues": [{
            "key": "PROJ-1",
            "fields": {"summary": "S", "status": {"name": "Open"},
                       "issuetype": {"name": "Bug"}, "priority": {"name": "High"},
                       "assignee": {"displayName": "John"}, "reporter": None, "updated": "x"},
        }]}
        mock_create.return_value = mock_jira

        jira_search(_search_args(project="PROJ"))
        out = capsys.readouterr().out
        assert "PROJ-1" in out
        assert "John" in out

    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_csv_output(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_jira.jql.return_value = {"issues": [{
            "key": "PROJ-1",
            "fields": {"summary": "S", "status": {"name": "Open"},
                       "issuetype": {"name": "Bug"}, "priority": {"name": "High"},
                       "assignee": None, "reporter": None, "updated": ""},
        }]}
        mock_create.return_value = mock_jira

        jira_search(_search_args(project="PROJ", csv=True))
        out = capsys.readouterr().out
        assert "key,status,type,priority,assignee,summary" in out
        assert "PROJ-1,Open,Bug,High,,S" in out


class TestJiraComment:
    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_add_comment_inline(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_create.return_value = mock_jira
        jira_comment(Namespace(issue_key="PROJ-1", body="Hello", body_file=None))
        mock_jira.issue_add_comment.assert_called_once_with("PROJ-1", "Hello")
        assert "PROJ-1" in capsys.readouterr().out

    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_add_comment_from_file(self, mock_create, tmp_path):
        mock_jira = MagicMock()
        mock_create.return_value = mock_jira
        f = tmp_path / "c.md"
        f.write_text("File body")
        jira_comment(Namespace(issue_key="PROJ-1", body=None, body_file=str(f)))
        mock_jira.issue_add_comment.assert_called_once_with("PROJ-1", "File body")

    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_missing_body_exits(self, mock_create):
        mock_create.return_value = MagicMock()
        with pytest.raises(SystemExit):
            jira_comment(Namespace(issue_key="PROJ-1", body=None, body_file=None))

    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_both_sources_exits(self, mock_create):
        mock_create.return_value = MagicMock()
        with pytest.raises(SystemExit):
            jira_comment(Namespace(issue_key="PROJ-1", body="x", body_file="f"))


class TestJiraComments:
    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_list(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_jira.issue_get_comments.return_value = {"comments": [
            {"id": "1", "author": {"displayName": "John"}, "created": "T", "body": "Hi"}
        ]}
        mock_create.return_value = mock_jira
        jira_comments(Namespace(issue_key="PROJ-1", json=False))
        out = capsys.readouterr().out
        assert "John" in out
        assert "Hi" in out

    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_empty(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_jira.issue_get_comments.return_value = {"comments": []}
        mock_create.return_value = mock_jira
        jira_comments(Namespace(issue_key="PROJ-1", json=False))
        assert "No comments" in capsys.readouterr().out


class TestJiraLink:
    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_link(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_create.return_value = mock_jira
        jira_link(Namespace(from_issue="A-1", to_issue="B-2", type="Blocks", comment=None))
        mock_jira.create_issue_link.assert_called_once_with({
            "type": {"name": "Blocks"},
            "inwardIssue": {"key": "A-1"},
            "outwardIssue": {"key": "B-2"},
        })
        assert "Linked" in capsys.readouterr().out

    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_link_with_comment(self, mock_create):
        mock_jira = MagicMock()
        mock_create.return_value = mock_jira
        jira_link(Namespace(from_issue="A-1", to_issue="B-2", type="Blocks", comment="see context"))
        body = mock_jira.create_issue_link.call_args[0][0]
        assert body["comment"] == {"body": "see context"}

    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_unlink(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_create.return_value = mock_jira
        jira_unlink(Namespace(link_id="42"))
        mock_jira.remove_issue_link.assert_called_once_with("42")

    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_link_types(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_jira.get_issue_link_types.return_value = {"issueLinkTypes": [
            {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
        ]}
        mock_create.return_value = mock_jira
        jira_link_types(Namespace(json=False))
        out = capsys.readouterr().out
        assert "Blocks" in out
        assert "blocks" in out


class TestParseTimeSpec:
    def test_hours_minutes(self):
        assert parse_time_spec("2h 30m") == 2 * 3600 + 30 * 60

    def test_days(self):
        assert parse_time_spec("1d") == 8 * 3600

    def test_weeks_days(self):
        assert parse_time_spec("1w 1d") == 5 * 8 * 3600 + 8 * 3600

    def test_bare_number_is_minutes(self):
        assert parse_time_spec("90") == 90 * 60

    def test_empty(self):
        assert parse_time_spec("") is None
        assert parse_time_spec(None) is None

    def test_invalid(self):
        with pytest.raises(ValueError):
            parse_time_spec("abc")


class TestJiraWorklog:
    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_logs_time(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_create.return_value = mock_jira
        jira_worklog(Namespace(issue_key="PROJ-1", time="2h", comment=None, started="2026-01-01T00:00:00.000+0000"))
        mock_jira.issue_worklog.assert_called_once_with("PROJ-1", "2026-01-01T00:00:00.000+0000", 7200, comment=None)
        assert "PROJ-1" in capsys.readouterr().out

    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_zero_time_exits(self, mock_create):
        mock_create.return_value = MagicMock()
        with pytest.raises(SystemExit):
            jira_worklog(Namespace(issue_key="PROJ-1", time="0m", comment=None, started=None))

    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_invalid_time_exits(self, mock_create):
        mock_create.return_value = MagicMock()
        with pytest.raises(SystemExit):
            jira_worklog(Namespace(issue_key="PROJ-1", time="bogus", comment=None, started=None))


class TestSprints:
    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_list_sprints(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_jira.get_all_sprints_from_board.return_value = {"values": [
            {"id": 1, "state": "active", "name": "Sprint 1"},
        ]}
        mock_create.return_value = mock_jira
        jira_sprints(Namespace(board="42", state=None, json=False))
        out = capsys.readouterr().out
        assert "Sprint 1" in out
        assert "active" in out

    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_sprint_add(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_create.return_value = mock_jira
        jira_sprint_add(Namespace(sprint_id="5", issue_keys=["A-1", "A-2"]))
        mock_jira.add_issues_to_sprint.assert_called_once_with("5", ["A-1", "A-2"])

    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_sprint_issues(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_jira.get_sprint_issues.return_value = {"issues": [
            {"key": "A-1", "fields": {"summary": "S", "status": {"name": "Open"}}},
        ]}
        mock_create.return_value = mock_jira
        jira_sprint_issues(Namespace(sprint_id="5", limit=50, json=False))
        out = capsys.readouterr().out
        assert "A-1" in out


class TestJiraClone:
    @patch("atlassian_local_cli.jira_extras.get_config")
    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_clone_basic(self, mock_create, mock_config, capsys):
        mock_config.return_value = MagicMock(jira_url="https://jira.test/")
        mock_jira = MagicMock()
        mock_jira.issue.return_value = {"fields": {
            "summary": "Original", "description": "Desc",
            "project": {"key": "PROJ"}, "issuetype": {"name": "Task"},
            "priority": {"name": "High"}, "labels": ["a"],
        }}
        mock_jira.issue_create.return_value = {"key": "PROJ-50"}
        mock_create.return_value = mock_jira

        jira_clone(Namespace(issue_key="PROJ-1", summary=None, replace=None))

        fields = mock_jira.issue_create.call_args[1]["fields"]
        assert fields["summary"] == "Original"
        assert fields["description"] == "Desc"
        assert fields["priority"] == {"name": "High"}
        assert fields["labels"] == ["a"]

    @patch("atlassian_local_cli.jira_extras.get_config")
    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_clone_with_replace(self, mock_create, mock_config):
        mock_config.return_value = MagicMock(jira_url="https://jira.test/")
        mock_jira = MagicMock()
        mock_jira.issue.return_value = {"fields": {
            "summary": "Original Q1", "description": "Q1 plan",
            "project": {"key": "P"}, "issuetype": {"name": "Task"},
        }}
        mock_jira.issue_create.return_value = {"key": "P-2"}
        mock_create.return_value = mock_jira

        jira_clone(Namespace(issue_key="P-1", summary=None, replace=["Q1:Q2"]))
        fields = mock_jira.issue_create.call_args[1]["fields"]
        assert fields["summary"] == "Original Q2"
        assert fields["description"] == "Q2 plan"

    @patch("atlassian_local_cli.jira_extras.get_config")
    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_clone_with_summary_override(self, mock_create, mock_config):
        mock_config.return_value = MagicMock(jira_url="https://jira.test/")
        mock_jira = MagicMock()
        mock_jira.issue.return_value = {"fields": {
            "summary": "Old", "project": {"key": "P"}, "issuetype": {"name": "Task"},
        }}
        mock_jira.issue_create.return_value = {"key": "P-3"}
        mock_create.return_value = mock_jira

        jira_clone(Namespace(issue_key="P-1", summary="Brand new", replace=None))
        assert mock_jira.issue_create.call_args[1]["fields"]["summary"] == "Brand new"


class TestJiraDelete:
    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_requires_yes(self, mock_create):
        mock_create.return_value = MagicMock()
        with pytest.raises(SystemExit):
            jira_delete(Namespace(issue_key="PROJ-1", yes=False, cascade=False))

    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_deletes_with_yes(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_create.return_value = mock_jira
        jira_delete(Namespace(issue_key="PROJ-1", yes=True, cascade=True))
        mock_jira.delete_issue.assert_called_once_with("PROJ-1", delete_subtasks=True)


class TestJiraEpics:
    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_lists_epics(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_jira.jql.return_value = {"issues": [
            {"key": "PROJ-100", "fields": {"summary": "Big", "status": {"name": "Open"}}},
        ]}
        mock_create.return_value = mock_jira
        jira_epics(Namespace(project="PROJ", status="open", limit=50, json=False))
        out = capsys.readouterr().out
        assert "PROJ-100" in out
        assert "Big" in out
        jql = mock_jira.jql.call_args[0][0]
        assert 'issuetype = "Epic"' in jql
        assert 'project = "PROJ"' in jql

    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_epic_issues_via_agile(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_jira.get.return_value = {"issues": [
            {"key": "PROJ-200", "fields": {"summary": "Child", "status": {"name": "Open"}}},
        ]}
        mock_create.return_value = mock_jira
        jira_epic_issues(Namespace(epic="PROJ-100", limit=50, json=False))
        assert "PROJ-200" in capsys.readouterr().out

    @patch("atlassian_local_cli.jira_extras._get_epic_fields", create=True)
    @patch("atlassian_local_cli.jira_commands._get_epic_fields")
    @patch("atlassian_local_cli.jira_extras.create_jira")
    def test_epic_issues_fallback_to_jql(self, mock_create, mock_get_epic_fields, _unused, capsys):
        mock_jira = MagicMock()
        mock_jira.get.side_effect = Exception("agile api unavailable")
        mock_jira.jql.return_value = {"issues": [
            {"key": "PROJ-201", "fields": {"summary": "Fallback", "status": {"name": "Open"}}},
        ]}
        mock_get_epic_fields.return_value = {"name": "cf_n", "link": "cf_l"}
        mock_create.return_value = mock_jira
        jira_epic_issues(Namespace(epic="PROJ-100", limit=50, json=False))
        out = capsys.readouterr().out
        assert "PROJ-201" in out
