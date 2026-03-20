import json
from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from atlassian_local_cli.jira_commands import (
    build_jql,
    jira_get,
    jira_my_tasks,
    jira_transition,
)


class TestBuildJql:
    def test_open_status(self):
        jql = build_jql(status="open")
        assert 'statusCategory != "Done"' in jql
        assert "assignee = currentUser()" in jql

    def test_closed_status(self):
        jql = build_jql(status="closed")
        assert 'statusCategory = "Done"' in jql

    def test_all_status(self):
        jql = build_jql(status="all")
        assert "statusCategory" not in jql

    def test_with_status_name(self):
        jql = build_jql(status_name="Reviewing")
        assert 'status = "Reviewing"' in jql

    def test_with_type(self):
        jql = build_jql(issue_type="Epic")
        assert 'issuetype = "Epic"' in jql

    def test_with_project(self):
        jql = build_jql(project="PROJ")
        assert 'project = "PROJ"' in jql

    def test_all_filters(self):
        jql = build_jql(status="closed", status_name="Done", issue_type="Task", project="PROJ")
        assert 'statusCategory = "Done"' in jql
        assert 'status = "Done"' in jql
        assert 'issuetype = "Task"' in jql
        assert 'project = "PROJ"' in jql
        assert jql.endswith("ORDER BY priority DESC, updated DESC")


MOCK_ISSUE = {
    "key": "PROJ-1",
    "fields": {
        "summary": "Test issue",
        "status": {"name": "Open"},
        "issuetype": {"name": "Task"},
        "priority": {"name": "High"},
        "assignee": {"displayName": "John Doe"},
        "reporter": {"displayName": "Jane Doe"},
        "created": "2026-01-01T00:00:00.000+0000",
        "updated": "2026-03-01T00:00:00.000+0000",
        "description": "A test description",
    },
}


class TestJiraGet:
    @patch("atlassian_local_cli.jira_commands.create_jira")
    def test_prints_fields(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_jira.issue.return_value = MOCK_ISSUE
        mock_create.return_value = mock_jira

        jira_get(Namespace(issue_key="PROJ-1"))
        output = capsys.readouterr().out
        assert "PROJ-1" in output
        assert "Test issue" in output
        assert "Open" in output
        assert "John Doe" in output
        assert "A test description" in output

    @patch("atlassian_local_cli.jira_commands.create_jira")
    def test_unassigned(self, mock_create, capsys):
        issue = {**MOCK_ISSUE, "fields": {**MOCK_ISSUE["fields"], "assignee": None}}
        mock_jira = MagicMock()
        mock_jira.issue.return_value = issue
        mock_create.return_value = mock_jira

        jira_get(Namespace(issue_key="PROJ-1"))
        output = capsys.readouterr().out
        assert "Unassigned" in output


class TestJiraMyTasks:
    @patch("atlassian_local_cli.jira_commands.create_jira")
    def test_table_format(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_jira.jql.return_value = {"issues": [MOCK_ISSUE]}
        mock_create.return_value = mock_jira

        args = Namespace(status="open", status_name=None, type=None, project=None, json=False, limit=50)
        jira_my_tasks(args)
        output = capsys.readouterr().out
        assert "PROJ-1" in output
        assert "Test issue" in output

    @patch("atlassian_local_cli.jira_commands.create_jira")
    def test_json_format(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_jira.jql.return_value = {"issues": [MOCK_ISSUE]}
        mock_create.return_value = mock_jira

        args = Namespace(status="open", status_name=None, type=None, project=None, json=True, limit=50)
        jira_my_tasks(args)
        output = capsys.readouterr().out
        data = json.loads(output)
        assert data[0]["key"] == "PROJ-1"

    @patch("atlassian_local_cli.jira_commands.create_jira")
    def test_empty(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_jira.jql.return_value = {"issues": []}
        mock_create.return_value = mock_jira

        args = Namespace(status="open", status_name=None, type=None, project=None, json=False, limit=50)
        jira_my_tasks(args)
        assert "No tasks assigned." in capsys.readouterr().out


class TestJiraTransition:
    @patch("atlassian_local_cli.jira_commands.create_jira")
    def test_list_transitions(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_jira.get_issue_transitions.return_value = [
            {"name": "In Progress", "id": "31"},
            {"name": "Done", "id": "41"},
        ]
        mock_create.return_value = mock_jira

        jira_transition(Namespace(issue_key="PROJ-1", status=None))
        output = capsys.readouterr().out
        assert "In Progress" in output
        assert "Done" in output

    @patch("atlassian_local_cli.jira_commands.create_jira")
    def test_transition_by_name(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_jira.get_issue_transitions.return_value = [
            {"name": "In Progress", "id": "31"},
        ]
        mock_create.return_value = mock_jira

        jira_transition(Namespace(issue_key="PROJ-1", status="in progress"))
        mock_jira.issue_transition.assert_called_once_with("PROJ-1", "31")

    @patch("atlassian_local_cli.jira_commands.create_jira")
    def test_transition_by_id(self, mock_create, capsys):
        mock_jira = MagicMock()
        mock_jira.get_issue_transitions.return_value = [
            {"name": "Done", "id": "41"},
        ]
        mock_create.return_value = mock_jira

        jira_transition(Namespace(issue_key="PROJ-1", status="41"))
        mock_jira.issue_transition.assert_called_once_with("PROJ-1", "41")

    @patch("atlassian_local_cli.jira_commands.create_jira")
    def test_invalid_transition_exits(self, mock_create):
        mock_jira = MagicMock()
        mock_jira.get_issue_transitions.return_value = [
            {"name": "Done", "id": "41"},
        ]
        mock_create.return_value = mock_jira

        with pytest.raises(SystemExit):
            jira_transition(Namespace(issue_key="PROJ-1", status="invalid"))
