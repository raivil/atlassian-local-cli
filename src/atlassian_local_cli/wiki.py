import os

import html2text

from .clients import create_confluence
from .config import get_config
from .converters import (
    extract_page_property_divs,
    extract_report_macros,
    extract_unknown_macros,
    extract_unsafe_tables,
    md_to_confluence_html,
    postprocess_export_md,
    preprocess_export_html,
    rewrite_local_images,
    serialize_passthrough_footer,
    strip_frontmatter_and_title,
)


def wiki_export(args):
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

    config = get_config()
    page_url = f"{config.wiki_url.rstrip('/')}/pages/viewpage.action?pageId={page['id']}"
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


def wiki_raw(args):
    """Dump a page's unconverted HTML. Use this when an export fails, hangs or loses
    content, to see what the converter was actually handed."""
    confluence = create_confluence()
    page = confluence.get_page_by_id(args.page_id, expand="body.export_view,body.storage,version,space")

    bodies = {
        "storage": page["body"]["storage"]["value"],
        "export_view": page["body"]["export_view"]["value"],
    }
    wanted = list(bodies) if args.format == "both" else [args.format]

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

    confluence = create_confluence()
    page = confluence.get_page_by_id(args.page_id, expand="version")
    title = title_from_file or page["title"]

    _upload_attachments(confluence, args.page_id, images)
    confluence.update_page(args.page_id, title, html_content, representation="storage")
    print(f"Updated page {args.page_id}: {title}")


def wiki_create(args):
    with open(args.input_file, "r", encoding="utf-8") as f:
        md_text = f.read()

    _, md_text = strip_frontmatter_and_title(md_text)
    html_content = md_to_confluence_html(md_text)
    base_dir = os.path.dirname(os.path.abspath(args.input_file))
    html_content, images = rewrite_local_images(html_content, base_dir)

    config = get_config()
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
    print(f"{config.wiki_url.rstrip('/')}/pages/viewpage.action?pageId={page_id}")
