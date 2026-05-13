"""Additional Jira commands inspired by ankitpokhrel/jira-cli."""

import json
import re
import sys
import webbrowser
from datetime import datetime, timezone

from .clients import create_jira
from .config import get_config


def _resolve_body(inline, file_path):
    """Resolve text content from inline arg or file (use '-' for stdin)."""
    if inline and file_path:
        print("Error: --body and --body-file are mutually exclusive.", file=sys.stderr)
        sys.exit(1)
    if file_path:
        if file_path == "-":
            return sys.stdin.read()
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    return inline


def _issue_url(issue_key):
    config = get_config()
    return f"{config.jira_url.rstrip('/')}/browse/{issue_key}"


def jira_me(args):
    jira = create_jira()
    user = jira.myself()
    if args.json:
        print(json.dumps(user, indent=2))
        return
    print(user.get("name") or user.get("accountId") or user.get("key", ""))


def jira_open(args):
    url = _issue_url(args.issue_key)
    if args.print_url:
        print(url)
        return
    webbrowser.open(url)
    print(url)


def build_search_jql(args):
    """Build JQL from --jql or filter flags. --jql wins; filter flags are AND-appended."""
    parts = []
    if args.jql:
        parts.append(f"({args.jql})")

    if args.assignee:
        if args.assignee.lower() == "me":
            parts.append("assignee = currentUser()")
        elif args.assignee.lower() == "none":
            parts.append("assignee is EMPTY")
        else:
            parts.append(f'assignee = "{args.assignee}"')

    if args.reporter:
        if args.reporter.lower() == "me":
            parts.append("reporter = currentUser()")
        else:
            parts.append(f'reporter = "{args.reporter}"')

    if args.status:
        if args.status == "open":
            parts.append('statusCategory != "Done"')
        elif args.status == "closed":
            parts.append('statusCategory = "Done"')

    if args.status_name:
        parts.append(f'status = "{args.status_name}"')

    if args.type:
        parts.append(f'issuetype = "{args.type}"')

    if args.priority:
        parts.append(f'priority = "{args.priority}"')

    if args.project:
        parts.append(f'project = "{args.project}"')

    for lbl in args.label or []:
        parts.append(f'labels = "{lbl}"')

    if not parts:
        return ""
    jql = " AND ".join(parts)

    if args.order_by:
        direction = "ASC" if args.reverse else "DESC"
        jql = f"{jql} ORDER BY {args.order_by} {direction}"
    elif not args.jql:
        # Default ordering only when not passing raw JQL
        jql = f"{jql} ORDER BY updated DESC"

    return jql


def jira_search(args):
    jira = create_jira()
    jql = build_search_jql(args)
    if not jql:
        print("Error: must provide --jql or at least one filter.", file=sys.stderr)
        sys.exit(1)

    issues = jira.jql(jql, limit=args.limit)["issues"]

    rows = []
    for issue in issues:
        f = issue["fields"]
        rows.append({
            "key": issue["key"],
            "summary": f.get("summary", ""),
            "status": (f.get("status") or {}).get("name", ""),
            "type": (f.get("issuetype") or {}).get("name", ""),
            "priority": (f.get("priority") or {}).get("name", ""),
            "assignee": (f.get("assignee") or {}).get("displayName", ""),
            "reporter": (f.get("reporter") or {}).get("displayName", ""),
            "updated": f.get("updated", ""),
        })

    if args.json:
        print(json.dumps(rows, indent=2))
        return
    if args.csv:
        import csv
        writer = csv.writer(sys.stdout)
        writer.writerow(["key", "status", "type", "priority", "assignee", "summary"])
        for r in rows:
            writer.writerow([r["key"], r["status"], r["type"], r["priority"], r["assignee"], r["summary"]])
        return

    if not rows:
        print("No issues found.")
        return

    kw = max(len(r["key"]) for r in rows)
    sw = max(len(r["status"]) for r in rows)
    tw = max(len(r["type"]) for r in rows)
    pw = max(len(r["priority"]) for r in rows)
    aw = max(len(r["assignee"]) for r in rows) or 1

    header = f"{'Key':<{kw}}  {'Status':<{sw}}  {'Type':<{tw}}  {'Priority':<{pw}}  {'Assignee':<{aw}}  Summary"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{r['key']:<{kw}}  {r['status']:<{sw}}  {r['type']:<{tw}}  {r['priority']:<{pw}}  {r['assignee']:<{aw}}  {r['summary']}")


def jira_comment(args):
    body = _resolve_body(args.body, args.body_file)
    if not body:
        print("Error: comment body is required (--body or --body-file).", file=sys.stderr)
        sys.exit(1)
    jira = create_jira()
    jira.issue_add_comment(args.issue_key, body)
    print(f"Comment added to {args.issue_key}")


def jira_comments(args):
    jira = create_jira()
    result = jira.issue_get_comments(args.issue_key)
    comments = result.get("comments", []) if isinstance(result, dict) else result

    if args.json:
        print(json.dumps(comments, indent=2))
        return

    if not comments:
        print(f"No comments on {args.issue_key}.")
        return

    for c in comments:
        author = (c.get("author") or {}).get("displayName", "Unknown")
        created = c.get("created", "")
        print(f"--- {author} @ {created} (id: {c.get('id')}) ---")
        print(c.get("body", "").rstrip())
        print()


def jira_link(args):
    jira = create_jira()
    data = {
        "type": {"name": args.type},
        "inwardIssue": {"key": args.from_issue},
        "outwardIssue": {"key": args.to_issue},
    }
    if args.comment:
        data["comment"] = {"body": args.comment}
    jira.create_issue_link(data)
    print(f"Linked {args.from_issue} {args.type} {args.to_issue}")


def jira_unlink(args):
    jira = create_jira()
    jira.remove_issue_link(args.link_id)
    print(f"Removed link {args.link_id}")


def jira_link_types(args):
    jira = create_jira()
    result = jira.get_issue_link_types()
    types = result.get("issueLinkTypes", []) if isinstance(result, dict) else result
    if args.json:
        print(json.dumps(types, indent=2))
        return
    if not types:
        print("No link types defined.")
        return
    for t in types:
        print(f"{t.get('name')}: {t.get('inward')} / {t.get('outward')}")


_TIME_UNITS = {"w": 5 * 8 * 3600, "d": 8 * 3600, "h": 3600, "m": 60}


def parse_time_spec(spec):
    """Parse a Jira-style time string ('1w 2d 3h 30m') into seconds.

    Uses Jira's standard work-week conventions: 1w = 5d, 1d = 8h."""
    if spec is None:
        return None
    spec = spec.strip()
    if not spec:
        return None
    if spec.isdigit():
        return int(spec) * 60  # bare number → minutes
    total = 0
    matched = False
    for value, unit in re.findall(r"(\d+)\s*([wdhm])", spec.lower()):
        total += int(value) * _TIME_UNITS[unit]
        matched = True
    if not matched:
        raise ValueError(f"Cannot parse time spec: {spec!r}")
    return total


def jira_worklog(args):
    jira = create_jira()
    try:
        seconds = parse_time_spec(args.time)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    if not seconds or seconds <= 0:
        print("Error: --time must be a positive duration (e.g. '2h 30m').", file=sys.stderr)
        sys.exit(1)
    started = args.started or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")
    jira.issue_worklog(args.issue_key, started, seconds, comment=args.comment)
    print(f"Logged {seconds // 60}m on {args.issue_key}")


def jira_sprints(args):
    jira = create_jira()
    result = jira.get_all_sprints_from_board(args.board, state=args.state)
    sprints = result.get("values", []) if isinstance(result, dict) else result
    if args.json:
        print(json.dumps(sprints, indent=2))
        return
    if not sprints:
        print(f"No sprints on board {args.board}.")
        return
    for s in sprints:
        print(f"{s.get('id')}\t{s.get('state', '')}\t{s.get('name', '')}")


def jira_sprint_add(args):
    jira = create_jira()
    jira.add_issues_to_sprint(args.sprint_id, list(args.issue_keys))
    print(f"Added {len(args.issue_keys)} issue(s) to sprint {args.sprint_id}")


def jira_sprint_issues(args):
    jira = create_jira()
    result = jira.get_sprint_issues(args.sprint_id, 0, args.limit)
    issues = result.get("issues", []) if isinstance(result, dict) else result
    if args.json:
        print(json.dumps(issues, indent=2))
        return
    if not issues:
        print(f"No issues in sprint {args.sprint_id}.")
        return
    for issue in issues:
        f = issue["fields"]
        print(f"{issue['key']}\t{(f.get('status') or {}).get('name', '')}\t{f.get('summary', '')}")


def _apply_replacements(text, replacements):
    if text is None:
        return None
    for r in replacements or []:
        if ":" not in r:
            raise ValueError(f"--replace expects 'find:replace', got '{r}'")
        find, repl = r.split(":", 1)
        text = text.replace(find, repl)
    return text


def jira_clone(args):
    jira = create_jira()
    source = jira.issue(args.issue_key)
    src_fields = source["fields"]

    try:
        summary = args.summary or _apply_replacements(src_fields.get("summary", ""), args.replace)
        description = _apply_replacements(src_fields.get("description"), args.replace)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    fields = {
        "project": {"key": src_fields["project"]["key"]},
        "summary": summary,
        "issuetype": {"name": src_fields["issuetype"]["name"]},
    }
    if description:
        fields["description"] = description
    if src_fields.get("priority"):
        fields["priority"] = {"name": src_fields["priority"]["name"]}
    if src_fields.get("labels"):
        fields["labels"] = list(src_fields["labels"])

    result = jira.issue_create(fields=fields)
    new_key = result["key"]
    print(f"Cloned {args.issue_key} → {new_key}: {summary}")
    print(_issue_url(new_key))


def jira_delete(args):
    jira = create_jira()
    if not args.yes:
        print(f"Refusing to delete {args.issue_key} without --yes.", file=sys.stderr)
        sys.exit(1)
    jira.delete_issue(args.issue_key, delete_subtasks=args.cascade)
    print(f"Deleted {args.issue_key}")


def jira_epics(args):
    jira = create_jira()
    jql_parts = ['issuetype = "Epic"']
    if args.project:
        jql_parts.append(f'project = "{args.project}"')
    if args.status == "open":
        jql_parts.append('statusCategory != "Done"')
    elif args.status == "closed":
        jql_parts.append('statusCategory = "Done"')
    jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"

    issues = jira.jql(jql, limit=args.limit)["issues"]
    if args.json:
        print(json.dumps([{"key": i["key"], "summary": i["fields"].get("summary", ""),
                            "status": (i["fields"].get("status") or {}).get("name", "")}
                          for i in issues], indent=2))
        return
    if not issues:
        print("No epics found.")
        return
    for issue in issues:
        f = issue["fields"]
        print(f"{issue['key']}\t{(f.get('status') or {}).get('name', '')}\t{f.get('summary', '')}")


def jira_epic_issues(args):
    """List issues linked to an Epic."""
    jira = create_jira()
    # Try Agile API first (works on Cloud and most Server); fall back to JQL on Epic Link.
    try:
        # GET /rest/agile/1.0/epic/{epicIdOrKey}/issue
        result = jira.get(f"rest/agile/1.0/epic/{args.epic}/issue", params={"maxResults": args.limit})
        issues = result.get("issues", []) if isinstance(result, dict) else []
    except Exception:
        issues = []

    if not issues:
        # Fallback: query by Epic Link custom field
        from .jira_commands import _get_epic_fields
        epic_fields = _get_epic_fields(jira)
        jql = f'"{epic_fields["link"]}" = {args.epic} ORDER BY updated DESC'
        issues = jira.jql(jql, limit=args.limit)["issues"]

    if args.json:
        print(json.dumps([{"key": i["key"], "summary": i["fields"].get("summary", ""),
                            "status": (i["fields"].get("status") or {}).get("name", "")}
                          for i in issues], indent=2))
        return
    if not issues:
        print(f"No issues found in epic {args.epic}.")
        return
    for issue in issues:
        f = issue["fields"]
        print(f"{issue['key']}\t{(f.get('status') or {}).get('name', '')}\t{f.get('summary', '')}")
