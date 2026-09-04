import argparse
import getpass
import os
import sys
from importlib.metadata import version

from .config import (
    DEFAULT_WIKI_URL,
    ContextExistsError,
    ContextNotFoundError,
    InvalidContextNameError,
    context_env_path,
    context_exists,
    get_current_context,
    list_contexts,
    load_config,
    resolve_context_name,
    set_active_context,
    set_current_context,
    validate_context_name,
    write_context_env,
)
from .jira_commands import (
    jira_create,
    jira_get,
    jira_link_epic,
    jira_my_tasks,
    jira_transition,
    jira_update,
)
from .jira_extras import (
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
)
from .wiki import (
    wiki_attachments,
    wiki_create,
    wiki_delete,
    wiki_export,
    wiki_raw,
    wiki_update,
)


def _context_list(args):
    contexts = list_contexts()
    if not contexts:
        print("No contexts configured.")
        print(f"Create one by adding {context_env_path('default')} or {context_env_path('<name>')}.")
        return
    active = resolve_context_name()
    persisted = get_current_context()
    for name in contexts:
        marker = "*" if name == active else " "
        suffix = ""
        if name == persisted:
            suffix = "  (current)"
        print(f"{marker} {name}{suffix}")


def _prompt(label, default=None, secret=False):
    # Non-interactive callers pass flags; anything they omit stays at its default
    # rather than blocking on a prompt that nobody can answer.
    if not sys.stdin.isatty():
        return default or ""
    suffix = f" [{default}]" if default else ""
    reader = getpass.getpass if secret else input
    try:
        return reader(f"{label}{suffix}: ").strip() or (default or "")
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled; no context was written.", file=sys.stderr)
        sys.exit(1)


CONTEXT_ADD_FIELDS = [
    ("WIKI_URL", "wiki_url", "WIKI_URL", DEFAULT_WIKI_URL, False),
    ("WIKI_USERNAME", "wiki_username", "WIKI_USERNAME (blank = Bearer auth)", None, False),
    ("WIKI_TOKEN", "wiki_token", "WIKI_TOKEN", None, True),
    ("JIRA_URL", "jira_url", "JIRA_URL", None, False),
    ("JIRA_USERNAME", "jira_username", "JIRA_USERNAME (email; blank = Bearer/PAT auth)", None, False),
    ("JIRA_TOKEN", "jira_token", "JIRA_TOKEN", None, True),
]


def _context_add(args):
    try:
        name = validate_context_name(args.name)
    except InvalidContextNameError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if context_exists(name) and not args.force:
        print(
            f"Error: context '{name}' already exists at {context_env_path(name)}. "
            "Pass --force to overwrite.",
            file=sys.stderr,
        )
        sys.exit(1)

    values = {}
    for key, attr, label, default, secret in CONTEXT_ADD_FIELDS:
        supplied = getattr(args, attr)
        values[key] = supplied if supplied is not None else _prompt(label, default, secret)

    if not values["JIRA_TOKEN"] and not values["WIKI_TOKEN"]:
        print(
            "Error: at least one of JIRA_TOKEN or WIKI_TOKEN is required; "
            "a context with neither cannot authenticate.",
            file=sys.stderr,
        )
        sys.exit(1)

    values["JIRA_EPIC_NAME_FIELD"] = args.jira_epic_name_field
    values["JIRA_EPIC_LINK_FIELD"] = args.jira_epic_link_field

    try:
        path = write_context_env(name, values, force=args.force)
    except (ContextExistsError, InvalidContextNameError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Shell env beats file values (see load_config), so a shadowed key would
    # silently defeat the context the user just created.
    shadowed = [k for k, v in values.items() if v and os.getenv(k)]
    if shadowed:
        plural = "s" if len(shadowed) > 1 else ""
        print(
            f"Warning: {', '.join(shadowed)} {'are' if plural else 'is'} also set in your shell "
            f"environment, which overrides this file. Unset {'them' if plural else 'it'} or this "
            "context won't take effect.",
            file=sys.stderr,
        )

    print(f"Wrote {path}")
    print("\nActivate it with:")
    print(f"  atlassian-local-cli context use {name}")
    print("Or for one command:")
    print(f"  atlassian-local-cli --context {name} jira-me")


def _context_current(args):
    print(resolve_context_name())


def _context_use(args):
    name = args.name
    if not context_exists(name):
        available = ", ".join(list_contexts()) or "(none)"
        print(f"Error: context '{name}' does not exist. Available: {available}", file=sys.stderr)
        print(f"Create it at: {context_env_path(name)}", file=sys.stderr)
        sys.exit(1)
    set_current_context(name)
    print(f"Switched to context '{name}'.")


def _context_unset(args):
    set_current_context(None)
    print("Cleared persistent context; defaulting to 'default'.")


def _mask(value: str | None) -> str:
    if not value:
        return "(unset)"
    if len(value) <= 8:
        return "***"
    return value[:4] + "…" + value[-4:]


def _context_show(args):
    name = args.name or resolve_context_name()
    try:
        config = load_config(context=name)
    except ContextNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    path = context_env_path(name)
    print(f"context: {name}")
    print(f"file:    {path}{' (missing)' if not path.exists() else ''}")
    print(f"WIKI_URL={config.wiki_url}")
    print(f"WIKI_USERNAME={config.wiki_username or '(unset)'}")
    print(f"WIKI_TOKEN={_mask(config.wiki_token)}")
    print(f"JIRA_URL={config.jira_url or '(unset)'}")
    print(f"JIRA_USERNAME={config.jira_username or '(unset)'}")
    print(f"JIRA_TOKEN={_mask(config.jira_token)}")
    if config.jira_epic_name_field:
        print(f"JIRA_EPIC_NAME_FIELD={config.jira_epic_name_field}")
    if config.jira_epic_link_field:
        print(f"JIRA_EPIC_LINK_FIELD={config.jira_epic_link_field}")


def main():
    parser = argparse.ArgumentParser(description="CLI for Confluence and Jira")
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"atlassian-local-cli {version('atlassian-local-cli')}",
    )
    parser.add_argument(
        "--context",
        help="Use a named context (overrides the persisted default). Run `context list` to see available contexts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ctx = subparsers.add_parser("context", help="Manage configuration contexts (accounts)")
    ctx_sub = ctx.add_subparsers(dest="context_command", required=True)

    cp = ctx_sub.add_parser("list", help="List available contexts")
    cp.set_defaults(func=_context_list)

    cp = ctx_sub.add_parser("current", help="Print the currently active context name")
    cp.set_defaults(func=_context_current)

    cp = ctx_sub.add_parser("add", help="Create a new context (prompts for anything not passed)")
    cp.add_argument("name", help="Context name, e.g. 'work'")
    cp.add_argument("--wiki-url")
    cp.add_argument("--wiki-username", help="Set for basic auth; omit for Bearer")
    cp.add_argument("--wiki-token")
    cp.add_argument("--jira-url")
    cp.add_argument("--jira-username", help="Atlassian Cloud email; omit for Server/DC Bearer PAT")
    cp.add_argument("--jira-token")
    cp.add_argument("--jira-epic-name-field")
    cp.add_argument("--jira-epic-link-field")
    cp.add_argument("--force", action="store_true", help="Overwrite an existing context")
    cp.set_defaults(func=_context_add)

    cp = ctx_sub.add_parser("use", help="Set the persistent default context")
    cp.add_argument("name", help="Context name (must already exist as contexts/<name>.env)")
    cp.set_defaults(func=_context_use)

    cp = ctx_sub.add_parser("unset", help="Clear the persistent default (revert to 'default')")
    cp.set_defaults(func=_context_unset)

    cp = ctx_sub.add_parser("show", help="Print resolved config for a context (tokens masked)")
    cp.add_argument("name", nargs="?", help="Context name (defaults to active)")
    cp.set_defaults(func=_context_show)

    p = subparsers.add_parser("wiki-export", help="Export a Confluence page to Markdown")
    p.add_argument("page_id", help="Confluence page ID")
    p.add_argument("-o", "--output", help="Output file (prints to stdout if omitted)")
    p.set_defaults(func=wiki_export)

    p = subparsers.add_parser("wiki-attachments", help="List or download a page's attachments")
    p.add_argument("page_id", help="Confluence page ID")
    p.add_argument("-o", "--output", metavar="DIR",
                   help="Download into this directory (lists to stdout if omitted)")
    p.add_argument("--match", metavar="GLOB", help="Only attachments whose filename matches this glob")
    p.add_argument("--json", action="store_true", help="Output the listing as JSON (ignored with -o)")
    p.set_defaults(func=wiki_attachments)

    p = subparsers.add_parser("wiki-raw", help="Dump a page's raw HTML (debug export problems)")
    p.add_argument("page_id", help="Confluence page ID")
    p.add_argument("--format", choices=["storage", "export", "both"], default="storage",
                   help="Which body to dump (default: storage)")
    p.add_argument("--macros", action="store_true", help="List top-level macros instead of dumping HTML")
    p.add_argument("-o", "--output", help="Output file (prints to stdout if omitted)")
    p.set_defaults(func=wiki_raw)

    p = subparsers.add_parser("wiki-update", help="Update a Confluence page from a Markdown file")
    p.add_argument("page_id", help="Confluence page ID")
    p.add_argument("input_file", help="Markdown file to upload")
    p.set_defaults(func=wiki_update)

    p = subparsers.add_parser("wiki-delete", help="Delete a Confluence page (moves to trash)")
    p.add_argument("page_id", help="Confluence page ID")
    p.add_argument("--yes", action="store_true", help="Confirm deletion (required)")
    p.add_argument("--cascade", action="store_true", help="Also delete child pages")
    p.set_defaults(func=wiki_delete)

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
    p.add_argument("--epic", help="Epic issue key to link this issue to (e.g. PROJ-100)")
    p.set_defaults(func=jira_create)

    p = subparsers.add_parser("jira-link-epic", help="Link existing issues to an Epic")
    p.add_argument("issue_keys", nargs="+", help="Issue keys to link (e.g. PROJ-200 PROJ-201)")
    p.add_argument("--epic", required=True, help="Epic issue key (e.g. PROJ-100)")
    p.set_defaults(func=jira_link_epic)

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

    p = subparsers.add_parser("jira-update", help="Update individual attributes of a Jira issue")
    p.add_argument("issue_key", help="Issue key (e.g. PROJ-123)")
    p.add_argument("--summary", help="New summary/title")
    p.add_argument("--description", help="Inline description (replaces existing)")
    p.add_argument("--description-file", help="Read description from file (use '-' for stdin)")
    p.add_argument("--priority", help="Priority (Highest, High, Medium, Low, Lowest)")
    p.add_argument("--assignee", help="Username to assign (pass 'none' to unassign)")
    p.add_argument("--type", help="Change issue type (e.g. Task, Bug, Story)")
    p.add_argument("--epic", help="Link to Epic issue key, or 'none' to unlink")
    p.add_argument("--label", action="append", help="Replace labels (repeatable)")
    p.add_argument("--add-label", action="append", help="Add a label (repeatable)")
    p.add_argument("--remove-label", action="append", help="Remove a label (repeatable)")
    p.add_argument("--field", action="append", help="Set raw field key=value (value parsed as JSON if possible). Repeatable.")
    p.set_defaults(func=jira_update)

    p = subparsers.add_parser("jira-transition", help="Transition a Jira issue to a new status")
    p.add_argument("issue_key", help="Issue key (e.g. PROJ-123)")
    p.add_argument("status", nargs="?", help="Target status name or transition ID (omit to list available)")
    p.add_argument(
        "--resolution",
        help="Set resolution during the transition, e.g. \"Won't Do\" (only valid on transitions whose screen includes the resolution field)",
    )
    p.set_defaults(func=jira_transition)

    p = subparsers.add_parser("jira-me", help="Print the current Jira user")
    p.add_argument("--json", action="store_true", help="Print full user JSON")
    p.set_defaults(func=jira_me)

    p = subparsers.add_parser("jira-open", help="Open a Jira issue in your browser")
    p.add_argument("issue_key", help="Issue key (e.g. PROJ-123)")
    p.add_argument("--print-url", action="store_true", help="Print URL only; don't open browser")
    p.set_defaults(func=jira_open)

    p = subparsers.add_parser("jira-search", help="Search Jira with JQL or filters")
    p.add_argument("--jql", help="Raw JQL (combined with filter flags via AND)")
    p.add_argument("--assignee", help="Filter by assignee (or 'me' / 'none')")
    p.add_argument("--reporter", help="Filter by reporter (or 'me')")
    p.add_argument("--status", choices=["open", "closed", "all"], help="Filter by status category")
    p.add_argument("--status-name", help="Filter by exact status name")
    p.add_argument("--type", help="Filter by issue type")
    p.add_argument("--priority", help="Filter by priority")
    p.add_argument("--project", help="Filter by project key")
    p.add_argument("--label", action="append", help="Filter by label (repeatable)")
    p.add_argument("--order-by", help="JQL field to order by (default: updated)")
    p.add_argument("--reverse", action="store_true", help="Order ASC instead of DESC")
    p.add_argument("--limit", type=int, default=50, help="Max results (default: 50)")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.add_argument("--csv", action="store_true", help="Output as CSV")
    p.set_defaults(func=jira_search)

    p = subparsers.add_parser("jira-comment", help="Add a comment to a Jira issue")
    p.add_argument("issue_key", help="Issue key (e.g. PROJ-123)")
    p.add_argument("--body", help="Inline comment body")
    p.add_argument("--body-file", help="Read comment from file (use '-' for stdin)")
    p.set_defaults(func=jira_comment)

    p = subparsers.add_parser("jira-comments", help="List comments on a Jira issue")
    p.add_argument("issue_key", help="Issue key (e.g. PROJ-123)")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=jira_comments)

    p = subparsers.add_parser("jira-link", help="Link two Jira issues with a relation type")
    p.add_argument("from_issue", help="Inward (source) issue key")
    p.add_argument("to_issue", help="Outward (target) issue key")
    p.add_argument("--type", required=True, help="Link type name (e.g. Blocks, Relates, Duplicates)")
    p.add_argument("--comment", help="Optional comment to add with the link")
    p.set_defaults(func=jira_link)

    p = subparsers.add_parser("jira-unlink", help="Remove an issue link by ID")
    p.add_argument("link_id", help="Issue link ID")
    p.set_defaults(func=jira_unlink)

    p = subparsers.add_parser("jira-link-types", help="List available Jira issue link types")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=jira_link_types)

    p = subparsers.add_parser("jira-worklog", help="Log work on a Jira issue")
    p.add_argument("issue_key", help="Issue key (e.g. PROJ-123)")
    p.add_argument("--time", required=True, help="Time spent (e.g. '2h 30m', '1d')")
    p.add_argument("--comment", help="Optional worklog comment")
    p.add_argument("--started", help="Start time in Jira format (default: now UTC)")
    p.set_defaults(func=jira_worklog)

    p = subparsers.add_parser("jira-sprints", help="List sprints on an Agile board")
    p.add_argument("--board", required=True, help="Board ID")
    p.add_argument("--state", help="Filter by state (active, closed, future)")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=jira_sprints)

    p = subparsers.add_parser("jira-sprint-add", help="Add issues to a sprint")
    p.add_argument("sprint_id", help="Sprint ID")
    p.add_argument("issue_keys", nargs="+", help="Issue keys to add")
    p.set_defaults(func=jira_sprint_add)

    p = subparsers.add_parser("jira-sprint-issues", help="List issues in a sprint")
    p.add_argument("sprint_id", help="Sprint ID")
    p.add_argument("--limit", type=int, default=50, help="Max results (default: 50)")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=jira_sprint_issues)

    p = subparsers.add_parser("jira-clone", help="Clone a Jira issue")
    p.add_argument("issue_key", help="Source issue key")
    p.add_argument("--summary", help="Override the summary on the clone")
    p.add_argument("--replace", action="append", help="Find:replace applied to summary/description (repeatable)")
    p.set_defaults(func=jira_clone)

    p = subparsers.add_parser("jira-delete", help="Delete a Jira issue")
    p.add_argument("issue_key", help="Issue key")
    p.add_argument("--yes", action="store_true", help="Confirm deletion (required)")
    p.add_argument("--cascade", action="store_true", help="Also delete sub-tasks")
    p.set_defaults(func=jira_delete)

    p = subparsers.add_parser("jira-epics", help="List Epic issues")
    p.add_argument("--project", help="Filter by project key")
    p.add_argument("--status", choices=["open", "closed", "all"], default="open", help="Filter by status (default: open)")
    p.add_argument("--limit", type=int, default=50, help="Max results (default: 50)")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=jira_epics)

    p = subparsers.add_parser("jira-epic-issues", help="List issues belonging to an Epic")
    p.add_argument("epic", help="Epic issue key (e.g. PROJ-100)")
    p.add_argument("--limit", type=int, default=50, help="Max results (default: 50)")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=jira_epic_issues)

    args = parser.parse_args()

    if args.context is not None:
        if not context_exists(args.context):
            available = ", ".join(list_contexts()) or "(none)"
            print(
                f"Error: context '{args.context}' does not exist. Available: {available}",
                file=sys.stderr,
            )
            print(f"Create it at: {context_env_path(args.context)}", file=sys.stderr)
            sys.exit(1)
        set_active_context(args.context)

    args.func(args)
