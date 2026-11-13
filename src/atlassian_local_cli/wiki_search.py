import html
import json
import re
import sys

from atlassian.errors import ApiValueError

from .clients import create_confluence

# Quoted strings are matched alongside ORDER BY so that one inside a string
# (`text ~ "sort order by date"`) is consumed as the string, not split as a clause.
_STRING_OR_ORDER_BY = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\border\s+by\b', re.I)
_HIGHLIGHT = re.compile(r"@@@(?:end)?hl@@@")


def _quote(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _split_order_by(cql):
    for match in _STRING_OR_ORDER_BY.finditer(cql):
        if match.group(0)[0] not in "\"'":
            return cql[:match.start()].strip(), cql[match.start():].strip()
    return cql.strip(), ""


def build_search_cql(args):
    """Build CQL from --cql and filter flags, AND-combined. A trailing ORDER BY in
    --cql is lifted out first: left inside the parentheses it is a parse error."""
    where, order = _split_order_by(args.cql or "")
    if order and args.order_by:
        raise ValueError("--cql already ends in ORDER BY; drop that or --order-by.")

    filters = []
    if args.text:
        filters.append(f"text ~ {_quote(args.text)}")
    if args.title:
        filters.append(f"title ~ {_quote(args.title)}")
    if args.space:
        filters.append(f"space = {_quote(args.space)}")
    if args.type:
        filters.append(f"type = {args.type}")
    if args.contributor:
        if args.contributor.lower() == "me":
            filters.append("contributor = currentUser()")
        else:
            filters.append(f"contributor = {_quote(args.contributor)}")
    if args.parent:
        filters.append(f"parent = {_quote(args.parent)}")
    if args.modified_since:
        filters.append(f"lastmodified >= {_quote(args.modified_since)}")

    if where and filters:
        where = f"({where})"
    clauses = ([where] if where else []) + filters
    if not clauses:
        return ""
    if args.order_by:
        order = f"order by {args.order_by} {'asc' if args.reverse else 'desc'}"
    return " AND ".join(clauses) + (f" {order}" if order else "")


def _search(confluence, cql, limit):
    """`cql()` is a single request, and a server may return fewer hits than asked
    for, so page on `start` until `limit` or `totalSize` is reached."""
    hits, total = [], 0
    while len(hits) < limit:
        page = confluence.cql(cql, start=len(hits), limit=limit - len(hits), expand="content.space")
        batch = page.get("results", [])
        total = page.get("totalSize", 0)
        hits.extend(batch)
        if not batch or len(hits) >= total:
            break
    return hits, max(total, len(hits))


def _clean(text):
    return " ".join(html.unescape(_HIGHLIGHT.sub("", text or "")).split())


def _row(hit, base_url):
    content = hit.get("content")
    if content:
        rid, rtype, title = content.get("id"), content.get("type", ""), content.get("title")
        space = (content.get("space") or {}).get("key", "")
    else:
        # Space (and user) hits carry no content, so there is no id to export.
        entity = hit.get("space") or {}
        rid, rtype, title, space = None, hit.get("entityType", ""), entity.get("name"), entity.get("key", "")
    return {
        "id": rid,
        "type": rtype,
        "title": title or _clean(hit.get("title")),
        "space": space,
        "url": base_url + hit.get("url", ""),
        "last_modified": hit.get("lastModified", ""),
        "excerpt": _clean(hit.get("excerpt")),
    }


def _print_table(rows):
    ids = [r["id"] or "-" for r in rows]
    iw = max(len("ID"), *(len(i) for i in ids))
    tw = max(len("Type"), *(len(r["type"]) for r in rows))
    sw = max(len("Space"), *(len(r["space"]) for r in rows))
    header = f"{'ID':<{iw}}  {'Type':<{tw}}  {'Space':<{sw}}  {'Modified':<10}  Title"
    print(header)
    print("-" * len(header))
    for rid, r in zip(ids, rows):
        print(f"{rid:<{iw}}  {r['type']:<{tw}}  {r['space']:<{sw}}  {r['last_modified'][:10]:<10}  {r['title']}")
        if r["excerpt"]:
            print(f"    {r['excerpt']}")


def wiki_search(args):
    if args.limit < 1:
        print("Error: --limit must be at least 1.", file=sys.stderr)
        sys.exit(1)
    try:
        cql = build_search_cql(args)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    if not cql:
        print("Error: must provide --cql or at least one filter.", file=sys.stderr)
        sys.exit(1)

    confluence = create_confluence()
    try:
        hits, total = _search(confluence, cql, args.limit)
    except ApiValueError as e:
        # The library replaces the server's reason with a generic "cannot be parsed".
        print(f"Error: Confluence rejected the query: {e.reason or e}", file=sys.stderr)
        print(f"CQL: {cql}", file=sys.stderr)
        sys.exit(1)

    base_url = confluence.url.rstrip("/")
    rows = [_row(hit, base_url) for hit in hits]

    if args.json:
        print(json.dumps(rows, indent=2))
    elif rows:
        _print_table(rows)
    else:
        print("No results found.")

    if total > len(rows):
        print(f"Showing {len(rows)} of {total} results; raise --limit for more.", file=sys.stderr)
