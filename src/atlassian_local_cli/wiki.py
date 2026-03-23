import os

import html2text

from .clients import create_confluence
from .config import get_config
from .converters import md_to_confluence_html, postprocess_export_md, preprocess_export_html, strip_frontmatter_and_title


def wiki_export(args):
    confluence = create_confluence()
    page = confluence.get_page_by_id(args.page_id, expand="body.export_view,version,space,history")

    html_content = preprocess_export_html(page["body"]["export_view"]["value"])
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = False
    h.ignore_emphasis = False

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
    content = f"{frontmatter}# {page['title']}\n\n{md_body}"

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

    title_from_file, md_text = strip_frontmatter_and_title(md_text)
    html_content = md_to_confluence_html(md_text)

    confluence = create_confluence()
    page = confluence.get_page_by_id(args.page_id, expand="version")
    title = title_from_file or page["title"]

    confluence.update_page(args.page_id, title, html_content, representation="storage")
    print(f"Updated page {args.page_id}: {title}")


def wiki_create(args):
    with open(args.input_file, "r", encoding="utf-8") as f:
        md_text = f.read()

    _, md_text = strip_frontmatter_and_title(md_text)
    html_content = md_to_confluence_html(md_text)

    config = get_config()
    confluence = create_confluence()
    result = confluence.create_page(
        space=args.space,
        title=args.title,
        body=html_content,
        parent_id=args.parent,
        representation="storage",
    )
    print(f"Created page {result['id']}: {args.title}")
    print(f"{config.wiki_url.rstrip('/')}/pages/viewpage.action?pageId={result['id']}")
