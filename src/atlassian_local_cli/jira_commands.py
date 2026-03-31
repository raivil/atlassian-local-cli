import json
import sys

from .clients import create_jira
from .config import get_config


_epic_fields_cache = {}


def _get_epic_fields(jira):
    """Auto-detect Epic custom field IDs, with env var overrides."""
    if _epic_fields_cache:
        return _epic_fields_cache

    config = get_config()
    epic_name_field = config.jira_epic_name_field
    epic_link_field = config.jira_epic_link_field

    if not epic_name_field or not epic_link_field:
        fields = jira.get_all_fields()
        for f in fields:
            name = f.get("name", "").lower()
            fid = f["id"]
            if not epic_name_field and name == "epic name":
                epic_name_field = fid
            if not epic_link_field and name == "epic link":
                epic_link_field = fid

    if not epic_name_field:
        print("Error: Could not detect Epic Name field. Set JIRA_EPIC_NAME_FIELD in .env.", file=sys.stderr)
        sys.exit(1)
    if not epic_link_field:
        print("Error: Could not detect Epic Link field. Set JIRA_EPIC_LINK_FIELD in .env.", file=sys.stderr)
        sys.exit(1)

    _epic_fields_cache["name"] = epic_name_field
    _epic_fields_cache["link"] = epic_link_field
    return _epic_fields_cache


def build_jql(status="open", status_name=None, issue_type=None, project=None):
    """Build JQL query from filter parameters."""
    conditions = ["assignee = currentUser()"]

    if status == "open":
        conditions.append('statusCategory != "Done"')
    elif status == "closed":
        conditions.append('statusCategory = "Done"')

    if status_name:
        conditions.append(f'status = "{status_name}"')

    if issue_type:
        conditions.append(f'issuetype = "{issue_type}"')

    if project:
        conditions.append(f'project = "{project}"')

    return " AND ".join(conditions) + " ORDER BY priority DESC, updated DESC"


def _resolve_description(args):
    """Resolve description from --description or --description-file (supports stdin via '-')."""
    if args.description and args.description_file:
        print("Error: --description and --description-file are mutually exclusive.", file=sys.stderr)
        sys.exit(1)

    if args.description_file:
        if args.description_file == "-":
            return sys.stdin.read()
        with open(args.description_file, "r", encoding="utf-8") as f:
            return f.read()

    return args.description


def jira_create(args):
    description = _resolve_description(args)

    jira = create_jira()

    fields = {
        "project": {"key": args.project},
        "summary": args.summary,
        "issuetype": {"name": args.type},
    }
    if description:
        fields["description"] = description
    if args.priority:
        fields["priority"] = {"name": args.priority}
    if args.assignee:
        fields["assignee"] = {"name": args.assignee}

    # Epic-specific fields
    if args.type == "Epic":
        epic_fields = _get_epic_fields(jira)
        fields[epic_fields["name"]] = args.summary

    if hasattr(args, "epic") and args.epic:
        epic_fields = _get_epic_fields(jira)
        fields[epic_fields["link"]] = args.epic

    result = jira.issue_create(fields=fields)

    issue_key = result["key"]
    config = get_config()
    print(f"Created {issue_key}: {args.summary}")
    print(f"{config.jira_url.rstrip('/')}/browse/{issue_key}")


def jira_link_epic(args):
    jira = create_jira()
    epic_fields = _get_epic_fields(jira)
    link_field = epic_fields["link"]

    for issue_key in args.issue_keys:
        jira.issue_update(issue_key, {"fields": {link_field: args.epic}})
        print(f"Linked {issue_key} \u2192 {args.epic}")


def jira_get(args):
    jira = create_jira()
    issue = jira.issue(args.issue_key)

    fields = issue["fields"]
    print(f"Key:         {issue['key']}")
    print(f"Summary:     {fields.get('summary', '')}")
    print(f"Status:      {fields.get('status', {}).get('name', '')}")
    print(f"Type:        {fields.get('issuetype', {}).get('name', '')}")
    print(f"Priority:    {fields.get('priority', {}).get('name', '')}")
    print(f"Assignee:    {(fields.get('assignee') or {}).get('displayName', 'Unassigned')}")
    print(f"Reporter:    {(fields.get('reporter') or {}).get('displayName', '')}")
    print(f"Created:     {fields.get('created', '')}")
    print(f"Updated:     {fields.get('updated', '')}")

    description = fields.get("description")
    if description:
        print(f"\n--- Description ---\n{description}")


def jira_my_tasks(args):
    jira = create_jira()
    jql = build_jql(args.status, args.status_name, args.type, args.project)
    issues = jira.jql(jql, limit=args.limit)["issues"]

    tasks = []
    for issue in issues:
        fields = issue["fields"]
        tasks.append({
            "key": issue["key"],
            "summary": fields.get("summary", ""),
            "status": fields.get("status", {}).get("name", ""),
            "type": fields.get("issuetype", {}).get("name", ""),
            "priority": fields.get("priority", {}).get("name", ""),
            "updated": fields.get("updated", ""),
        })

    if args.json:
        print(json.dumps(tasks, indent=2))
    else:
        if not tasks:
            print("No tasks assigned.")
            return
        kw = max(len(t["key"]) for t in tasks)
        sw = max(len(t["status"]) for t in tasks)
        tw = max(len(t["type"]) for t in tasks)
        pw = max(len(t["priority"]) for t in tasks)

        header = f"{'Key':<{kw}}  {'Status':<{sw}}  {'Type':<{tw}}  {'Priority':<{pw}}  Summary"
        print(header)
        print("-" * len(header))
        for t in tasks:
            print(f"{t['key']:<{kw}}  {t['status']:<{sw}}  {t['type']:<{tw}}  {t['priority']:<{pw}}  {t['summary']}")


def jira_transition(args):
    jira = create_jira()

    if not args.status:
        transitions = jira.get_issue_transitions(args.issue_key)
        print(f"Available transitions for {args.issue_key}:")
        for t in transitions:
            print(f"  - {t['name']} (id: {t['id']})")
        return

    transitions = jira.get_issue_transitions(args.issue_key)
    target = args.status.lower()
    match = None
    for t in transitions:
        if t["name"].lower() == target or t["id"] == args.status:
            match = t
            break

    if not match:
        names = ", ".join(t["name"] for t in transitions)
        print(f"Error: '{args.status}' is not a valid transition. Available: {names}", file=sys.stderr)
        sys.exit(1)

    jira.issue_transition(args.issue_key, match["id"])
    print(f"Transitioned {args.issue_key} \u2192 {match['name']}")
