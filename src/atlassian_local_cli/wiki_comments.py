import json
import sys

import html2text

from .clients import create_confluence
from .converters import md_to_confluence_html
from .text_input import resolve_body

COMMENT_PAGE_SIZE = 50
COMMENT_EXPAND = "body.export_view,body.view,body.storage,version,history,ancestors,extensions"


def _iter_comments(confluence, page_id, location=None):
    """Yield every comment on a page. `get_page_comments` defaults to 25 per
    response and does not page, so a busy page would lose the older half."""
    start = 0
    while True:
        response = confluence.get_page_comments(
            content_id=page_id,
            expand=COMMENT_EXPAND,
            depth="all",
            location=location,
            start=start,
            limit=COMMENT_PAGE_SIZE,
        )
        results = (response or {}).get("results") or []
        yield from results
        if len(results) < COMMENT_PAGE_SIZE:
            return
        start += len(results)


def _html_to_md(html):
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = False
    h.ignore_emphasis = False
    h.body_width = 0
    return h.handle(html or "").strip()


def _comment_body_html(comment):
    """Prefer a rendered body. In storage format a code block is an
    `ac:structured-macro`, which html2text reduces to the bare language name and
    drops the CDATA payload; the rendered bodies carry a real `<pre>` instead."""
    body = comment.get("body") or {}
    for representation in ("export_view", "view", "storage"):
        value = (body.get(representation) or {}).get("value")
        if value:
            return value
    return ""


def _comment_author(comment):
    history = comment.get("history") or {}
    version = comment.get("version") or {}
    by = history.get("createdBy") or version.get("by") or {}
    return by.get("displayName") or by.get("username") or "Unknown"


def _comment_when(comment):
    history = comment.get("history") or {}
    return history.get("createdDate") or (comment.get("version") or {}).get("when") or ""


def wiki_comments(args):
    confluence = create_confluence()
    location = None if args.location == "all" else args.location
    comments = list(_iter_comments(confluence, args.page_id, location))

    if args.json:
        print(json.dumps(comments, indent=2))
        return

    if not comments:
        print(f"No comments on page {args.page_id}.")
        return

    for comment in comments:
        indent = "  " * len(comment.get("ancestors") or [])
        header = f"--- {_comment_author(comment)} @ {_comment_when(comment)} (id: {comment.get('id')}) ---"
        print(f"{indent}{header}")
        body = _html_to_md(_comment_body_html(comment))
        for line in body.splitlines():
            print(f"{indent}{line}" if line else "")
        print()


def wiki_comment(args):
    body = resolve_body(args.body, args.body_file)
    if not body:
        print("Error: comment body is required (--body or --body-file).", file=sys.stderr)
        sys.exit(1)

    confluence = create_confluence()
    # add_comment posts its argument as body.storage, so markdown has to be
    # converted first or it lands on the page as literal ** and -.
    result = confluence.add_comment(args.page_id, md_to_confluence_html(body))
    print(f"Comment added to page {args.page_id} (id: {(result or {}).get('id')})")


def wiki_comment_delete(args):
    if not args.yes:
        print(f"Refusing to delete comment {args.comment_id} without --yes.", file=sys.stderr)
        sys.exit(1)

    confluence = create_confluence()
    # Comment and page ids are indistinguishable by eye, and remove_content will
    # delete either one — so confirm what this id actually points at first.
    content = confluence.get_page_by_id(args.comment_id) or {}
    if content.get("type") != "comment":
        print(
            f"Refusing to delete {args.comment_id}: content type is "
            f"{content.get('type')!r}, not 'comment'.",
            file=sys.stderr,
        )
        sys.exit(1)

    confluence.remove_content(args.comment_id)
    print(f"Deleted comment {args.comment_id}")
