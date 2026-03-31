import argparse

from .jira_commands import jira_create, jira_get, jira_my_tasks, jira_transition
from .wiki import wiki_create, wiki_export, wiki_update


def main():
    parser = argparse.ArgumentParser(description="CLI for Confluence and Jira")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p = subparsers.add_parser("wiki-export", help="Export a Confluence page to Markdown")
    p.add_argument("page_id", help="Confluence page ID")
    p.add_argument("-o", "--output", help="Output file (prints to stdout if omitted)")
    p.set_defaults(func=wiki_export)

    p = subparsers.add_parser("wiki-update", help="Update a Confluence page from a Markdown file")
    p.add_argument("page_id", help="Confluence page ID")
    p.add_argument("input_file", help="Markdown file to upload")
    p.set_defaults(func=wiki_update)

    p = subparsers.add_parser("wiki-create", help="Create a new Confluence page from a Markdown file")
    p.add_argument("space", help="Space key (e.g. DEV)")
    p.add_argument("title", help="Page title")
    p.add_argument("input_file", help="Markdown file with page content")
    p.add_argument("--parent", help="Parent page ID (optional)")
    p.set_defaults(func=wiki_create)

    p = subparsers.add_parser("jira-create", help="Create a new Jira issue")
    p.add_argument("--project", required=True, help="Project key (e.g. PROJ)")
    p.add_argument("--summary", required=True, help="Issue summary/title")
    p.add_argument("--type", default="Task", help="Issue type (default: Task)")
    p.add_argument("--description", help="Inline description")
    p.add_argument("--description-file", help="Read description from file (use '-' for stdin)")
    p.add_argument("--priority", help="Priority (Highest, High, Medium, Low, Lowest)")
    p.add_argument("--assignee", help="Username to assign")
    p.set_defaults(func=jira_create)

    p = subparsers.add_parser("jira-get", help="Display a Jira issue")
    p.add_argument("issue_key", help="Issue key (e.g. PROJ-123)")
    p.set_defaults(func=jira_get)

    p = subparsers.add_parser("jira-my-tasks", help="List your assigned Jira tasks")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.add_argument("--limit", type=int, default=50, help="Max results (default: 50)")
    p.add_argument("--status", choices=["open", "closed", "all"], default="open", help="Filter by status category (default: open)")
    p.add_argument("--status-name", help="Filter by exact status name (e.g. Reviewing, \"In Progress\")")
    p.add_argument("--type", help="Filter by issue type (e.g. Task, Epic, Bug, Story)")
    p.add_argument("--project", help="Filter by project key (e.g. PROJ)")
    p.set_defaults(func=jira_my_tasks)

    p = subparsers.add_parser("jira-transition", help="Transition a Jira issue to a new status")
    p.add_argument("issue_key", help="Issue key (e.g. PROJ-123)")
    p.add_argument("status", nargs="?", help="Target status name or transition ID (omit to list available)")
    p.set_defaults(func=jira_transition)

    args = parser.parse_args()
    args.func(args)
