import fnmatch
import json
import os
import re
import sys

import html2text

from .clients import create_confluence
from .converters import (
    extract_page_property_divs,
    extract_report_macros,
    extract_unknown_macros,
    extract_unsafe_tables,
    md_to_confluence_html,
    postprocess_export_md,
    preprocess_export_html,
    rewrite_attachment_images,
    rewrite_local_images,
    serialize_passthrough_footer,
    strip_frontmatter_and_title,
)


def _page_url(confluence, page_id):
    """Build a page URL from the client's base, not WIKI_URL: Cloud serves
    Confluence under /wiki, which the client appends but WIKI_URL never carries.
    Using WIKI_URL produced frontmatter and create output that 404s on Cloud."""
    return f"{confluence.url.rstrip('/')}/pages/viewpage.action?pageId={page_id}"


def wiki_export(args):
    if args.attachments and not args.output:
        print("Error: --attachments needs -o/--output; there is no directory to download into.", file=sys.stderr)
        sys.exit(1)

    confluence = create_confluence()
    page = confluence.get_page_by_id(args.page_id, expand="body.export_view,body.storage,version,space,history")

    export_html = page["body"]["export_view"]["value"]
    storage_html = page["body"]["storage"]["value"]

    # Extract unknown macros and replace with placeholders in export_view
    export_html, passthrough_mapping = extract_unknown_macros(export_html, storage_html)

    # Page Properties (details) + Page Properties Report (detailssummary): replace the
    # rendered output with editable markdown directives. This also removes the rendered
    # copy from the body, so these macros are no longer duplicated on round-trip.
    export_html, page_property_blocks = extract_page_property_divs(export_html, storage_html)
    export_html, report_blocks = extract_report_macros(export_html, storage_html)

    # Tables whose cells hold block content (headings, lists, multiple paragraphs,
    # non-inline macros) can't survive a markdown round-trip — html2text renders
    # them across multiple lines, producing GFM-invalid tables that leak cell
    # content out of the table on re-import. Preserve those tables verbatim via the
    # passthrough footer instead. Runs after the page-property/report tables are
    # removed so the remaining export tables map 1:1 to storage tables.
    export_html, unsafe_table_mapping = extract_unsafe_tables(
        export_html, storage_html, start_counter=len(passthrough_mapping)
    )
    passthrough_mapping = {**passthrough_mapping, **unsafe_table_mapping}

    referenced_files = []
    if args.attachments:
        export_html, referenced_files = rewrite_attachment_images(export_html)

    html_content = preprocess_export_html(export_html)
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = False
    h.ignore_emphasis = False
    # html2text's own "don't wrap table rows" check looks for a space before the pipe,
    # but its generated rows are "cell1| cell2" (no leading space) — so long cells get
    # word-wrapped across lines with no way to tell a wrapped continuation from a real
    # row boundary on reimport. Disabling wrapping entirely avoids that ambiguity.
    h.body_width = 0

    page_url = _page_url(confluence, page["id"])
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

    md_body = postprocess_export_md(h.handle(html_content))
    # Restore page-properties / report directive tokens (unique, so order is irrelevant).
    for token, block in {**page_property_blocks, **report_blocks}.items():
        md_body = md_body.replace(token, block)
    passthrough_footer = serialize_passthrough_footer(passthrough_mapping)
    content = f"{frontmatter}# {page['title']}\n\n{md_body}{passthrough_footer}"

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Exported to {args.output}")
    else:
        print(content)

    if args.attachments:
        _download_referenced_attachments(
            confluence, args.page_id, referenced_files, os.path.dirname(args.output) or "."
        )


RAW_FORMAT_BODIES = {"storage": "storage", "export": "export_view"}


def wiki_raw(args):
    """Dump a page's unconverted HTML. Use this when an export fails, hangs or loses
    content, to see what the converter was actually handed."""
    confluence = create_confluence()
    page = confluence.get_page_by_id(args.page_id, expand="body.export_view,body.storage,version,space")

    bodies = {
        "storage": page["body"]["storage"]["value"],
        "export_view": page["body"]["export_view"]["value"],
    }
    wanted = list(bodies) if args.format == "both" else [RAW_FORMAT_BODIES[args.format]]

    if args.macros:
        from .converters import _find_top_level_macros

        macros = _find_top_level_macros(bodies["storage"])
        lines = [f"{len(macros)} top-level macro(s) in storage:"]
        lines += [f"  {name or '(unnamed)'}{'  [self-closing]' if xml.rstrip().endswith('/>') else ''}" for name, xml in macros]
        content = "\n".join(lines) + "\n"
    else:
        content = "".join(f"<!-- ===== {k} ===== -->\n{bodies[k]}\n" for k in wanted)

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Wrote {args.output}")
    else:
        print(content)


ATTACHMENT_PAGE_SIZE = 50


def _iter_attachments(confluence, page_id):
    """Yield every attachment on a page. The REST endpoint caps each response at
    `limit`, and the library's own download helper never pages past the first
    batch — so pages with more than 50 files silently lose the rest."""
    start = 0
    while True:
        response = confluence.get_attachments_from_content(
            page_id=page_id, start=start, limit=ATTACHMENT_PAGE_SIZE, expand="version"
        )
        results = (response or {}).get("results") or []
        yield from results
        if len(results) < ATTACHMENT_PAGE_SIZE:
            return
        start += len(results)


def _human_size(num_bytes):
    size = float(num_bytes or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def _attachment_summary(attachment):
    extensions = attachment.get("extensions") or {}
    version = attachment.get("version") or {}
    return {
        "id": attachment.get("id"),
        "title": attachment.get("title"),
        "media_type": extensions.get("mediaType"),
        "size": extensions.get("fileSize"),
        "version": version.get("number"),
        "updated": version.get("when"),
        "download_url": (attachment.get("_links") or {}).get("download"),
    }


def _safe_attachment_name(title, attachment_id, taken):
    """Attachment titles come from the server, so they can carry separators or
    `..` segments that would write outside the download directory."""
    base = os.path.basename((title or "").replace("\\", "/").strip())
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base)
    if base in ("", ".", ".."):
        base = attachment_id or "attachment"

    stem, ext = os.path.splitext(base)
    name, counter = base, 1
    while name.lower() in taken:
        name = f"{stem} ({counter}){ext}"
        counter += 1
    taken.add(name.lower())
    return name


def _download_attachments(confluence, attachments, directory):
    os.makedirs(directory, exist_ok=True)
    root = os.path.realpath(directory)
    taken = set()
    written = 0
    for attachment in attachments:
        name = _safe_attachment_name(attachment["title"], attachment["id"], taken)
        dest = os.path.join(directory, name)
        # Catches a pre-existing symlink in the directory pointing somewhere else.
        if os.path.realpath(dest) != os.path.join(root, name):
            print(f"  Skipping {name}: resolves outside {directory}", file=sys.stderr)
            continue
        content = confluence.get(attachment["download_url"], not_json_response=True)
        with open(dest, "wb") as f:
            f.write(content)
        written += 1
        print(f"  Downloaded {name} ({_human_size(len(content))})")

    plural = "" if written == 1 else "s"
    print(f"{written} attachment{plural} -> {directory}")


def wiki_attachments(args):
    confluence = create_confluence()
    attachments = [_attachment_summary(a) for a in _iter_attachments(confluence, args.page_id)]
    if args.match:
        attachments = [a for a in attachments if fnmatch.fnmatch(a["title"] or "", args.match)]

    if args.json:
        print(json.dumps(attachments, indent=2))
        return

    if not attachments:
        if args.match:
            print(f"No attachments matching {args.match!r} on page {args.page_id}.")
        else:
            print(f"No attachments on page {args.page_id}.")
        return

    if args.output:
        _download_attachments(confluence, attachments, args.output)
        return

    name_width = max(len(a["title"] or "") for a in attachments)
    size_width = max(len(_human_size(a["size"])) for a in attachments)
    type_width = max(len(a["media_type"] or "?") for a in attachments)
    for a in attachments:
        print(
            f"{a['title'] or '':<{name_width}}  {_human_size(a['size']):>{size_width}}  "
            f"{a['media_type'] or '?':<{type_width}}  v{a['version']}  {(a['updated'] or '')[:10]}"
        )
    total = sum(a["size"] or 0 for a in attachments)
    plural = "" if len(attachments) == 1 else "s"
    print(f"{len(attachments)} attachment{plural}, {_human_size(total)} total")


def _download_referenced_attachments(confluence, page_id, filenames, directory):
    """Fetch the attachments the rewritten markdown now points at. Anything the
    page references but does not own — a cross-page ri:page reference — is named
    rather than skipped silently, since wiki-update would upload a dead link."""
    if not filenames:
        return

    available = {}
    for attachment in _iter_attachments(confluence, page_id):
        summary = _attachment_summary(attachment)
        available[summary["title"]] = summary

    found = [available[name] for name in filenames if name in available]
    if found:
        _download_attachments(confluence, found, directory)
    for name in filenames:
        if name not in available:
            print(f"  Warning: {name} is referenced by the page but is not an attachment of it.", file=sys.stderr)


def _warn_unresolved_images(html):
    """A relative <img src> that survived rewrite_local_images had no file on
    disk. Confluence cannot resolve a relative path, so the upload would replace
    a working image with a broken one — say so rather than doing it quietly."""
    for tag in re.findall(r"<img\b[^>]*>", html):
        src = re.search(r'src="([^"]+)"', tag)
        if src and not src.group(1).startswith(("http://", "https://", "//", "data:", "/")):
            print(
                f"  Warning: {src.group(1)} not found on disk; the page will show a broken image.",
                file=sys.stderr,
            )


def _upload_attachments(confluence, page_id, images):
    for filename, abs_path in images:
        confluence.attach_file(abs_path, page_id=page_id, name=filename)
        print(f"  Uploaded attachment: {filename}")


def wiki_update(args):
    with open(args.input_file, "r", encoding="utf-8") as f:
        md_text = f.read()

    title_from_file, md_text = strip_frontmatter_and_title(md_text)
    html_content = md_to_confluence_html(md_text)
    base_dir = os.path.dirname(os.path.abspath(args.input_file))
    html_content, images = rewrite_local_images(html_content, base_dir)
    _warn_unresolved_images(html_content)

    confluence = create_confluence()
    page = confluence.get_page_by_id(args.page_id, expand="version")
    title = title_from_file or page["title"]

    _upload_attachments(confluence, args.page_id, images)
    confluence.update_page(args.page_id, title, html_content, representation="storage")
    print(f"Updated page {args.page_id}: {title}")


def wiki_delete(args):
    confluence = create_confluence()
    if not args.yes:
        print(f"Refusing to delete page {args.page_id} without --yes.", file=sys.stderr)
        sys.exit(1)
    page = confluence.get_page_by_id(args.page_id)
    confluence.remove_page(args.page_id, recursive=args.cascade)
    print(f"Deleted page {args.page_id}: {page['title']}")


def wiki_create(args):
    with open(args.input_file, "r", encoding="utf-8") as f:
        md_text = f.read()

    _, md_text = strip_frontmatter_and_title(md_text)
    html_content = md_to_confluence_html(md_text)
    base_dir = os.path.dirname(os.path.abspath(args.input_file))
    html_content, images = rewrite_local_images(html_content, base_dir)
    _warn_unresolved_images(html_content)

    confluence = create_confluence()
    result = confluence.create_page(
        space=args.space,
        title=args.title,
        body=html_content,
        parent_id=args.parent,
        representation="storage",
    )
    page_id = result["id"]
    _upload_attachments(confluence, page_id, images)
    print(f"Created page {page_id}: {args.title}")
    print(_page_url(confluence, page_id))
