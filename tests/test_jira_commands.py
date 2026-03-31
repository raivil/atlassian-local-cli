import json
from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from atlassian_local_cli.jira_commands import (
    _epic_fields_cache,
    _get_epic_fields,
    build_jql,
    jira_create,
    jira_get,
    jira_link_epic,
    jira_my_tasks,
    jira_transition,
)


@pytest.fixture(autouse=True)
def _clear_epic_cache():
    _epic_fields_cache.clear()
    yield
    _epic_fields_cache.clear()


MOCK_FIELDS = [
    {"id": "customfield_10004", "name": "Epic Name"},
    {"id": "customfield_10008", "name": "Epic Link"},
    {"id": "summary", "name": "Summary"},
]


class TestGetEpicFields:
    @patch("atlassian_local_cli.jira_commands.get_config")
    def test_auto_detect(self, mock_config):
        mock_config.return_value = MagicMock(jira_epic_name_field=None, jira_epic_link_field=None)
        mock_jira = MagicMock()
        mock_jira.get_all_fields.return_value = MOCK_FIELDS

        result = _get_epic_fields(mock_jira)
        assert result["name"] == "customfield_10004"
        assert result["link"] == "customfield_10008"

    @patch("atlassian_local_cli.jira_commands.get_config")
    def test_env_override(self, mock_config):
        mock_config.return_value = MagicMock(jira_epic_name_field="cf_100", jira_epic_link_field="cf_200")
        mock_jira = MagicMock()

        result = _get_epic_fields(mock_jira)
        assert result["name"] == "cf_100"
        assert result["link"] == "cf_200"
        mock_jira.get_all_fields.assert_not_called()

    @patch("atlassian_local_cli.jira_commands.get_config")
    def test_caches_result(self, mock_config):
        mock_config.return_value = MagicMock(jira_epic_name_field="cf_1", jira_epic_link_field="cf_2")
        mock_jira = MagicMock()

        result1 = _get_epic_fields(mock_jira)
        result2 = _get_epic_fields(mock_jira)
        assert result1 is result2

    @patch("atlassian_local_cli.jira_commands.get_config")
    def test_missing_epic_name_exits(self, mock_config):
        mock_config.return_value = MagicMock(jira_epic_name_field=None, jira_epic_link_field=None)
        mock_jira = MagicMock()
        mock_jira.get_all_fields.return_value = [{"id": "summary", "name": "Summary"}]

        with pytest.raises(SystemExit):
            _get_epic_fields(mock_jira)

    @patch("atlassian_local_cli.jira_commands.get_config")
    def test_missing_epic_link_exits(self, mock_config):
        mock_config.return_value = MagicMock(jira_epic_name_field=None, jira_epic_link_field=None)
        mock_jira = MagicMock()
        mock_jira.get_all_fields.return_value = [
            {"id": "customfield_10004", "name": "Epic Name"},
        ]

        with pytest.raises(SystemExit):
            _get_epic_fields(mock_jira)


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


class TestJiraCreate:
    @patch("atlassian_local_cli.jira_commands.get_config")
    @patch("atlassian_local_cli.jira_commands.create_jira")
    def test_basic_create(self, mock_create, mock_config, capsys):
        mock_config.return_value = MagicMock(jira_url="https://jira.test.com/")
        mock_jira = MagicMock()
        mock_jira.issue_create.return_value = {"key": "PROJ-99"}
        mock_create.return_value = mock_jira

        args = Namespace(
            project="PROJ", summary="New task", type="Task",
            description="Short desc", description_file=None,
            priority=None, assignee=None,
        )
        jira_create(args)
        output = capsys.readouterr().out
        assert "PROJ-99" in output
        assert "New task" in output

        fields = mock_jira.issue_create.call_args[1]["fields"]
        assert fields["project"] == {"key": "PROJ"}
        assert fields["summary"] == "New task"
        assert fields["description"] == "Short desc"

    @patch("atlassian_local_cli.jira_commands.get_config")
    @patch("atlassian_local_cli.jira_commands.create_jira")
    def test_with_priority_and_assignee(self, mock_create, mock_config):
        mock_config.return_value = MagicMock(jira_url="https://jira.test.com/")
        mock_jira = MagicMock()
        mock_jira.issue_create.return_value = {"key": "PROJ-100"}
        mock_create.return_value = mock_jira

        args = Namespace(
            project="PROJ", summary="Bug", type="Bug",
            description=None, description_file=None,
            priority="High", assignee="jdoe",
        )
        jira_create(args)

        fields = mock_jira.issue_create.call_args[1]["fields"]
        assert fields["priority"] == {"name": "High"}
        assert fields["assignee"] == {"name": "jdoe"}
        assert "description" not in fields

    @patch("atlassian_local_cli.jira_commands.get_config")
    @patch("atlassian_local_cli.jira_commands.create_jira")
    def test_description_from_file(self, mock_create, mock_config, tmp_path):
        mock_config.return_value = MagicMock(jira_url="https://jira.test.com/")
        mock_jira = MagicMock()
        mock_jira.issue_create.return_value = {"key": "PROJ-101"}
        mock_create.return_value = mock_jira

        desc_file = tmp_path / "desc.md"
        desc_file.write_text("Line 1\n\nLine 2\n\n- bullet\n- items")

        args = Namespace(
            project="PROJ", summary="From file", type="Task",
            description=None, description_file=str(desc_file),
            priority=None, assignee=None,
        )
        jira_create(args)

        fields = mock_jira.issue_create.call_args[1]["fields"]
        assert "Line 1" in fields["description"]
        assert "Line 2" in fields["description"]
        assert "- bullet" in fields["description"]

    @patch("atlassian_local_cli.jira_commands.get_config")
    @patch("atlassian_local_cli.jira_commands.create_jira")
    def test_description_from_stdin(self, mock_create, mock_config, monkeypatch):
        mock_config.return_value = MagicMock(jira_url="https://jira.test.com/")
        mock_jira = MagicMock()
        mock_jira.issue_create.return_value = {"key": "PROJ-102"}
        mock_create.return_value = mock_jira

        import io
        monkeypatch.setattr("sys.stdin", io.StringIO("Piped\nmultiline\ncontent"))

        args = Namespace(
            project="PROJ", summary="From stdin", type="Task",
            description=None, description_file="-",
            priority=None, assignee=None,
        )
        jira_create(args)

        fields = mock_jira.issue_create.call_args[1]["fields"]
        assert "Piped\nmultiline\ncontent" == fields["description"]

    def test_description_and_file_mutually_exclusive(self):
        args = Namespace(
            project="PROJ", summary="Test", type="Task",
            description="inline", description_file="file.md",
            priority=None, assignee=None, epic=None,
        )
        with pytest.raises(SystemExit):
            jira_create(args)

    @patch("atlassian_local_cli.jira_commands.get_config")
    @patch("atlassian_local_cli.jira_commands.create_jira")
    def test_create_epic(self, mock_create, mock_config):
        mock_config.return_value = MagicMock(
            jira_url="https://jira.test.com/",
            jira_epic_name_field="customfield_10004",
            jira_epic_link_field="customfield_10008",
        )
        mock_jira = MagicMock()
        mock_jira.issue_create.return_value = {"key": "PROJ-200"}
        mock_create.return_value = mock_jira

        args = Namespace(
            project="PROJ", summary="Auth Rewrite", type="Epic",
            description=None, description_file=None,
            priority=None, assignee=None, epic=None,
        )
        jira_create(args)

        fields = mock_jira.issue_create.call_args[1]["fields"]
        assert fields["issuetype"] == {"name": "Epic"}
        assert fields["customfield_10004"] == "Auth Rewrite"

    @patch("atlassian_local_cli.jira_commands.get_config")
    @patch("atlassian_local_cli.jira_commands.create_jira")
    def test_create_with_epic_link(self, mock_create, mock_config):
        mock_config.return_value = MagicMock(
            jira_url="https://jira.test.com/",
            jira_epic_name_field="customfield_10004",
            jira_epic_link_field="customfield_10008",
        )
        mock_jira = MagicMock()
        mock_jira.issue_create.return_value = {"key": "PROJ-201"}
        mock_create.return_value = mock_jira

        args = Namespace(
            project="PROJ", summary="Add MFA", type="Story",
            description=None, description_file=None,
            priority=None, assignee=None, epic="PROJ-200",
        )
        jira_create(args)

        fields = mock_jira.issue_create.call_args[1]["fields"]
        assert fields["customfield_10008"] == "PROJ-200"


class TestJiraLinkEpic:
    @patch("atlassian_local_cli.jira_commands.get_config")
    @patch("atlassian_local_cli.jira_commands.create_jira")
    def test_link_single_issue(self, mock_create, mock_config, capsys):
        mock_config.return_value = MagicMock(
            jira_epic_name_field="customfield_10004",
            jira_epic_link_field="customfield_10008",
        )
        mock_jira = MagicMock()
        mock_create.return_value = mock_jira

        jira_link_epic(Namespace(issue_keys=["PROJ-201"], epic="PROJ-200"))

        mock_jira.issue_update.assert_called_once_with(
            "PROJ-201", {"fields": {"customfield_10008": "PROJ-200"}}
        )
        assert "PROJ-201" in capsys.readouterr().out

    @patch("atlassian_local_cli.jira_commands.get_config")
    @patch("atlassian_local_cli.jira_commands.create_jira")
    def test_link_multiple_issues(self, mock_create, mock_config, capsys):
        mock_config.return_value = MagicMock(
            jira_epic_name_field="customfield_10004",
            jira_epic_link_field="customfield_10008",
        )
        mock_jira = MagicMock()
        mock_create.return_value = mock_jira

        jira_link_epic(Namespace(issue_keys=["PROJ-201", "PROJ-202", "PROJ-203"], epic="PROJ-200"))

        assert mock_jira.issue_update.call_count == 3
        output = capsys.readouterr().out
        assert "PROJ-201" in output
        assert "PROJ-202" in output
        assert "PROJ-203" in output
