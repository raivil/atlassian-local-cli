import argparse
import json
import os
import re
import sys
from pathlib import Path

import html2text
import markdown as md_lib
from atlassian import Confluence, Jira
from dotenv import load_dotenv

CONFIG_DIR = Path.home() / ".config" / "atlassian-local-cli"

load_dotenv(CONFIG_DIR / ".env")

WIKI_URL = os.getenv("WIKI_URL", "https://wiki.example.com/")
WIKI_USERNAME = os.getenv("WIKI_USERNAME")
WIKI_TOKEN = os.getenv("WIKI_TOKEN")

JIRA_URL = os.getenv("JIRA_URL")
JIRA_USERNAME = os.getenv("JIRA_USERNAME")
JIRA_TOKEN = os.getenv("JIRA_TOKEN")


def _confluence():
    if not WIKI_TOKEN:
        print(f"Error: WIKI_TOKEN is not set. Add it to {CONFIG_DIR / '.env'} or export it.", file=sys.stderr)
        sys.exit(1)
    if WIKI_USERNAME:
        return Confluence(url=WIKI_URL, username=WIKI_USERNAME, password=WIKI_TOKEN)
    import requests
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {WIKI_TOKEN}"
    return Confluence(url=WIKI_URL, session=session)


def _jira():
    if not JIRA_URL or not JIRA_TOKEN:
        print(f"Error: JIRA_URL and JIRA_TOKEN must be set. Add them to {CONFIG_DIR / '.env'} or export them.", file=sys.stderr)
        sys.exit(1)
    import requests
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {JIRA_TOKEN}"
    return Jira(url=JIRA_URL, session=session)


def _md_to_confluence_html(md_text):
    """Convert markdown to Confluence storage format HTML."""
    html = md_lib.markdown(md_text, extensions=["tables", "fenced_code"])
    # Convert <pre><code class="language-X"> to Confluence code macro
    html = re.sub(
        r'<pre><code class="language-(\w+)">(.*?)</code></pre>',
        lambda m: (
            f'<ac:structured-macro ac:name="code">'
            f'<ac:parameter ac:name="language">{m.group(1)}</ac:parameter>'
            f'<ac:plain-text-body><![CDATA[{_unescape_html(m.group(2))}]]></ac:plain-text-body>'
            f'</ac:structured-macro>'
        ),
        html,
        flags=re.DOTALL,
    )
    # Convert <pre><code> (no language) to Confluence code macro
    html = re.sub(
        r'<pre><code>(.*?)</code></pre>',
        lambda m: (
            f'<ac:structured-macro ac:name="code">'
            f'<ac:plain-text-body><![CDATA[{_unescape_html(m.group(1))}]]></ac:plain-text-body>'
            f'</ac:structured-macro>'
        ),
        html,
        flags=re.DOTALL,
    )
    return html


def _unescape_html(text):
    """Unescape HTML entities inside code blocks for CDATA."""
    return (text
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"'))


def _strip_frontmatter_and_title(md_text):
    """Strip YAML frontmatter and title heading, return (title, body)."""
    # Strip frontmatter if present
    fm_match = re.match(r"^---\n.*?\n---\n\n?", md_text, re.DOTALL)
    if fm_match:
        md_text = md_text[fm_match.end():]

    # Strip title heading
    title = None
    title_match = re.match(r"^# (.+)\n\n", md_text)
    if title_match:
        title = title_match.group(1).strip()
        md_text = md_text[title_match.end():]

    return title, md_text


# -- Wiki commands --

def wiki_export(args):
    confluence = _confluence()
    page = confluence.get_page_by_id(args.page_id, expand="body.export_view,version,space,history")

    html_content = page["body"]["export_view"]["value"]
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = False
    h.ignore_emphasis = False

    page_url = f"{WIKI_URL.rstrip('/')}/pages/viewpage.action?pageId={page['id']}"
    frontmatter = (
        f"---\n"
        f"page_id: \"{page['id']}\"\n"
        f"space: {page['space']['key']}\n"
        f"version: {page['version']['number']}\n"
        f"author: {page['history']['createdBy']['displayName']}\n"
        f"created: {page['history']['createdDate']}\n"
        f"updated: {page['version']['when']}\n"
        f"url: {page_url}\n"
        f"---\n\n"
    )

    content = f"{frontmatter}# {page['title']}\n\n{h.handle(html_content)}"

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Exported to {args.output}")
    else:
        print(content)


def wiki_update(args):
    with open(args.input_file, "r", encoding="utf-8") as f:
        md_text = f.read()

    title_from_file, md_text = _strip_frontmatter_and_title(md_text)
    html_content = _md_to_confluence_html(md_text)

    confluence = _confluence()
    page = confluence.get_page_by_id(args.page_id, expand="version")
    title = title_from_file or page["title"]

    confluence.update_page(args.page_id, title, html_content, representation="storage")
    print(f"Updated page {args.page_id}: {title}")


def wiki_create(args):
    with open(args.input_file, "r", encoding="utf-8") as f:
        md_text = f.read()

    _, md_text = _strip_frontmatter_and_title(md_text)
    html_content = _md_to_confluence_html(md_text)

    confluence = _confluence()
    result = confluence.create_page(
        space=args.space,
        title=args.title,
        body=html_content,
        parent_id=args.parent,
        representation="storage",
    )
    print(f"Created page {result['id']}: {args.title}")
    print(f"{WIKI_URL.rstrip('/')}/pages/viewpage.action?pageId={result['id']}")


# -- Jira commands --

def jira_get(args):
    jira = _jira()
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
    jira = _jira()

    conditions = ["assignee = currentUser()"]

    if args.status == "open":
        conditions.append('statusCategory != "Done"')
    elif args.status == "closed":
        conditions.append('statusCategory = "Done"')
    # "all" adds no status filter

    if args.status_name:
        conditions.append(f'status = "{args.status_name}"')

    if args.type:
        conditions.append(f'issuetype = "{args.type}"')

    if args.project:
        conditions.append(f'project = "{args.project}"')

    jql = " AND ".join(conditions) + " ORDER BY priority DESC, updated DESC"
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
        # Column widths
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
    jira = _jira()

    # List available transitions if no target status given
    if not args.status:
        transitions = jira.get_issue_transitions(args.issue_key)
        print(f"Available transitions for {args.issue_key}:")
        for t in transitions:
            print(f"  - {t['name']} (id: {t['id']})")
        return

    # Find matching transition
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
    print(f"Transitioned {args.issue_key} → {match['name']}")


def main():
    parser = argparse.ArgumentParser(description="CLI for Confluence and Jira")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- wiki export --
    p = subparsers.add_parser("wiki-export", help="Export a Confluence page to Markdown")
    p.add_argument("page_id", help="Confluence page ID")
    p.add_argument("-o", "--output", help="Output file (prints to stdout if omitted)")
    p.set_defaults(func=wiki_export)

    # -- wiki update --
    p = subparsers.add_parser("wiki-update", help="Update a Confluence page from a Markdown file")
    p.add_argument("page_id", help="Confluence page ID")
    p.add_argument("input_file", help="Markdown file to upload")
    p.set_defaults(func=wiki_update)

    # -- wiki create --
    p = subparsers.add_parser("wiki-create", help="Create a new Confluence page from a Markdown file")
    p.add_argument("space", help="Space key (e.g. DEV)")
    p.add_argument("title", help="Page title")
    p.add_argument("input_file", help="Markdown file with page content")
    p.add_argument("--parent", help="Parent page ID (optional)")
    p.set_defaults(func=wiki_create)

    # -- jira get --
    p = subparsers.add_parser("jira-get", help="Display a Jira issue")
    p.add_argument("issue_key", help="Issue key (e.g. PROJ-123)")
    p.set_defaults(func=jira_get)

    # -- jira my-tasks --
    p = subparsers.add_parser("jira-my-tasks", help="List your assigned Jira tasks")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.add_argument("--limit", type=int, default=50, help="Max results (default: 50)")
    p.add_argument("--status", choices=["open", "closed", "all"], default="open", help="Filter by status category (default: open)")
    p.add_argument("--status-name", help="Filter by exact status name (e.g. Reviewing, \"In Progress\")")
    p.add_argument("--type", help="Filter by issue type (e.g. Task, Epic, Bug, Story)")
    p.add_argument("--project", help="Filter by project key (e.g. PROJ)")
    p.set_defaults(func=jira_my_tasks)

    # -- jira transition --
    p = subparsers.add_parser("jira-transition", help="Transition a Jira issue to a new status")
    p.add_argument("issue_key", help="Issue key (e.g. PROJ-123)")
    p.add_argument("status", nargs="?", help="Target status name or transition ID (omit to list available)")
    p.set_defaults(func=jira_transition)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
