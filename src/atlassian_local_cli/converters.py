import os
import re
from collections import defaultdict
from urllib.parse import unquote, urlsplit

import html2text
import markdown as md_lib
from bs4 import BeautifulSoup

# Macro names handled explicitly by the converters (so the generic passthrough
# mechanism skips them). "details" (Page Properties) and "detailssummary"
# (Page Properties Report) get dedicated round-trip handling.
KNOWN_MACRO_TYPES = {
    "status", "code", "info", "note", "warning", "tip", "panel", "jira",
    "expand", "toc", "details", "detailssummary",
}
PASSTHROUGH_PREFIX = "CONFLUENCE-PASSTHROUGH-"
MD_EXTENSIONS = ["tables", "fenced_code", "footnotes"]

# Sentinel placed in empty table cells before html2text and stripped afterwards.
# html2text renders an empty leading/trailing <th>/<td> as a bare edge pipe, which GFM
# treats as an optional delimiter — the cell collapses and the row no longer matches the
# separator's column count (Python-Markdown then refuses the whole table). SOH-wrapped so
# it can never collide with real page content. See _fill_empty_table_cells /
# _restore_empty_table_cells.
EMPTY_CELL_SENTINEL = "\x01EMPTYCELL\x01"

LOZENGE_TO_COLOUR = {
    "aui-lozenge-success": "green",
    "aui-lozenge-error": "red",
    "aui-lozenge-current": "blue",
    "aui-lozenge-moved": "yellow",
}

COLOUR_TO_CONFLUENCE = {
    "green": "Green",
    "red": "Red",
    "blue": "Blue",
    "yellow": "Yellow",
    "grey": "Grey",
}


_task_placeholder_store = {}


def _convert_task_list(inner_html):
    """Convert Confluence inline-task-list items to markdown checkbox placeholders."""
    items = re.findall(r'<li[^>]*class="(checked)"[^>]*>(.*?)</li>|<li[^>]*>(.*?)</li>', inner_html, re.DOTALL)
    lines = []
    for checked_class, checked_content, unchecked_content in items:
        if checked_class:
            text = re.sub(r'<[^>]+>', '', checked_content).strip()
            lines.append(f"TASK-CHECKED: {text}")
        else:
            text = re.sub(r'<[^>]+>', '', unchecked_content).strip()
            lines.append(f"TASK-UNCHECKED: {text}")
    # Return as paragraphs so html2text preserves them as separate lines
    return "<br/>".join(lines)


def _macro_name(xml):
    m = re.search(r'ac:name="([^"]*)"', xml)
    return m.group(1) if m else ""


# Opening tag (captures a trailing "/" for self-closing macros) or a closing tag.
_MACRO_TOKEN_RE = re.compile(r"<ac:structured-macro\b[^>]*?(/?)>|</ac:structured-macro>")


def _find_top_level_macros(storage_html):
    """Find all top-level ac:structured-macro elements, honouring nesting.

    Single forward pass over open/close/self-closing tokens. A self-closing macro
    (`<ac:structured-macro ... />`, e.g. `children`) has no close tag, so it must not
    count towards nesting depth — treating it as an opener leaves the depth unbalanced
    and the element unterminated.
    """
    results = []
    depth = 0
    start = None
    for m in _MACRO_TOKEN_RE.finditer(storage_html):
        token = m.group(0)
        if token.startswith("</"):
            if depth == 0:  # stray close tag
                continue
            depth -= 1
            if depth == 0 and start is not None:
                xml = storage_html[start:m.end()]
                results.append((_macro_name(xml), xml))
                start = None
        elif m.group(1) == "/":  # self-closing: a complete element on its own
            if depth == 0:
                results.append((_macro_name(token), token))
        else:
            if depth == 0:
                start = m.start()
            depth += 1
    return results


def _find_legacy_macros(storage_html):
    """Find top-level legacy <ac:macro> elements (older Confluence macro storage form).

    Without this, legacy macros (e.g. some detailssummary usages) are silently
    dropped on round-trip because they are neither known nor structured-macros.
    """
    results = []
    for m in re.finditer(r'<ac:macro\b[^>]*?/>|<ac:macro\b.*?</ac:macro>', storage_html, re.DOTALL):
        xml = m.group(0)
        name_match = re.search(r'ac:name="([^"]*)"', xml)
        results.append((name_match.group(1) if name_match else "", xml))
    return results


def extract_unknown_macros(export_html, storage_html):
    """Extract unknown macros from storage XML, return export_html unchanged and mapping."""
    mapping = {}
    counter = 0

    for name, xml in _find_top_level_macros(storage_html) + _find_legacy_macros(storage_html):
        if name not in KNOWN_MACRO_TYPES:
            marker = f"{PASSTHROUGH_PREFIX}{counter}"
            mapping[marker] = xml
            counter += 1

    return export_html, mapping


def serialize_passthrough_footer(mapping):
    """Generate HTML comment block to append to markdown for passthrough macros."""
    if not mapping:
        return ""
    blocks = []
    for marker, xml in mapping.items():
        blocks.append(f"<!-- confluence-passthrough\n{marker}:\n{xml}\n:{marker} -->")
    return "\n<!-- confluence-passthrough-start -->\n" + "\n".join(blocks) + "\n<!-- confluence-passthrough-stop -->\n"


def extract_passthrough_footer(md_text):
    """Extract passthrough blocks from markdown footer, return (cleaned text, mapping)."""
    match = re.search(
        r'\n<!-- confluence-passthrough-start -->\n(.*?)\n<!-- confluence-passthrough-stop -->\n?',
        md_text,
        re.DOTALL,
    )
    if not match:
        return md_text, {}

    footer = match.group(1)
    cleaned = md_text[:match.start()] + md_text[match.end():]

    mapping = {}
    for block in re.finditer(
        r'<!-- confluence-passthrough\n(' + re.escape(PASSTHROUGH_PREFIX) + r'\d+):\n(.*?)\n:\1 -->',
        footer,
        re.DOTALL,
    ):
        mapping[block.group(1)] = block.group(2)

    return cleaned, mapping


def restore_passthrough_blocks(html, mapping):
    """Replace passthrough marker placeholders in HTML with raw storage XML.
    If a marker isn't found in the body, append the macro at the end."""
    remaining = []
    for marker, xml in mapping.items():
        if f"<p>{marker}</p>" in html:
            html = html.replace(f"<p>{marker}</p>", xml)
        elif marker in html:
            html = html.replace(marker, xml)
        else:
            remaining.append(xml)
    if remaining:
        html += "\n".join(remaining)
    return html


def _status_span_to_token(m):
    classes = m.group(1)
    title = m.group(2)
    colour = "grey"
    for cls, col in LOZENGE_TO_COLOUR.items():
        if cls in classes:
            colour = col
            break
    return f"{{status:{title}|{colour}}}"


def convert_inline_confluence_tokens(html):
    """Convert status badges, user mentions, and dates to markdown tokens.

    Shared by the whole-page export preprocessing and per-cell page-properties export.
    """
    html = re.sub(
        r'<span[^>]*class="(status-macro[^"]*)"[^>]*>([^<]*)</span>',
        _status_span_to_token,
        html,
    )
    html = re.sub(
        r'<a[^>]*confluence-userlink[^>]*data-username="([^"]*)"[^>]*>[^<]*</a>',
        r"@\1",
        html,
    )
    # Dates: <time datetime="2026-03-26" ...>26 Mar 2026</time> → {date:2026-03-26}
    html = re.sub(
        r'<time[^>]*datetime="([^"]*)"[^>]*>[^<]*</time>',
        r"{date:\1}",
        html,
    )
    return html


def _fill_empty_table_cells(html):
    """Fill empty `<td>`/`<th>` cells with a sentinel so html2text can't drop them.

    An empty leading or trailing cell renders as a bare edge pipe that GFM discards,
    leaving the row with fewer columns than the table separator (and Python-Markdown then
    refuses to parse the table at all). The sentinel is removed again in
    `postprocess_export_md`. Only touches pages that actually have empty cells — otherwise
    the input string is returned unchanged.
    """
    if "<t" not in html:  # no <table>/<td>/<th> at all — cheap bail-out
        return html
    soup = BeautifulSoup(html, "html.parser")
    changed = False
    for cell in soup.find_all(["td", "th"]):
        if cell.get_text(strip=True) or cell.find("img"):
            continue  # has text or an image → not empty
        cell.clear()
        cell.append(EMPTY_CELL_SENTINEL)
        changed = True
    return str(soup) if changed else html


def preprocess_export_html(html):
    """Convert Confluence-specific HTML elements to markdown-friendly tokens before html2text."""

    # Confluence TOC macro renders as a div with class "toc-macro" (and often its inner list).
    # Replace with [TOC] marker, which postprocess keeps as-is.
    html = re.sub(
        r'<div[^>]*class="[^"]*\btoc-macro\b[^"]*"[^>]*>.*?</div>',
        "[TOC]",
        html,
        flags=re.DOTALL,
    )

    html = convert_inline_confluence_tokens(html)

    # Task lists inside table cells: convert to compact inline format
    # (markdown checkboxes can't live inside table cells)
    def _convert_task_list_inline(m):
        td_before = m.group(1)
        task_html = m.group(2)
        td_after = m.group(3)
        items = re.findall(r'<li[^>]*class="(checked)"[^>]*>(.*?)</li>|<li[^>]*>(.*?)</li>', task_html, re.DOTALL)
        parts = []
        for checked_class, checked_content, unchecked_content in items:
            if checked_class:
                text = re.sub(r'<[^>]+>', '', checked_content).strip()
                parts.append(f"[x] {text}")
            else:
                text = re.sub(r'<[^>]+>', '', unchecked_content).strip()
                parts.append(f"[ ] {text}")
        return f'{td_before}{"; ".join(parts)}{td_after}'

    html = re.sub(
        r'(<td[^>]*>)(?:\s*<[^>]*>)*\s*<ul[^>]*class="inline-task-list"[^>]*>(.*?)</ul>(?:\s*<[^>]*>)*\s*(</td>)',
        _convert_task_list_inline,
        html,
        flags=re.DOTALL,
    )

    # Standalone task lists: convert to markdown checkbox placeholders
    html = re.sub(
        r'<ul[^>]*class="inline-task-list"[^>]*>(.*?)</ul>',
        lambda m: _convert_task_list(m.group(1)),
        html,
        flags=re.DOTALL,
    )

    # Expand/collapse sections — process BEFORE panels to prevent panels from consuming expand content.
    # Uses BeautifulSoup for reliable nested div handling.
    soup = BeautifulSoup(html, "html.parser")
    expand_counter = [0]
    for container in soup.find_all("div", class_="expand-container"):
        title_span = container.find("span", class_="expand-control-text")
        content_div = container.find("div", class_="expand-content")
        if title_span and content_div:
            title = title_span.get_text(strip=True)
            body = re.sub(r'<[^>]+>', '', content_div.decode_contents()).strip()
            marker = f"EXPAND-START: {title}<br/>EXPAND-BODY: {body}<br/>EXPAND-END"
            container.replace_with(BeautifulSoup(marker, "html.parser"))
            expand_counter[0] += 1
    if expand_counter[0]:
        html = str(soup)

    # Info/note/warning/tip panels
    _MACRO_TYPE_MAP = {
        "information": "info",
        "note": "note",
        "warning": "warning",
        "tip": "tip",
    }

    def _replace_panel(m):
        classes = m.group(1)
        title_html = m.group(2) or ""
        body_html = m.group(3)
        panel_type = "info"
        for suffix, ptype in _MACRO_TYPE_MAP.items():
            if f"macro-{suffix}" in classes:
                panel_type = ptype
                break
        title = re.sub(r'<[^>]+>', '', title_html).strip()
        body = re.sub(r'<[^>]+>', '', body_html).strip()
        header = f"{{panel:{panel_type}|{title}}}" if title else f"{{panel:{panel_type}}}"
        return f"PANEL-START: {header}<br/>PANEL-BODY: {body}<br/>PANEL-END"

    html = re.sub(
        r'<div[^>]*class="(confluence-information-macro[^"]*)"[^>]*>'
        r'(?:<p[^>]*class="title[^"]*"[^>]*>(.*?)</p>)?'
        r'.*?<div[^>]*class="confluence-information-macro-body"[^>]*>(.*?)</div>\s*</div>',
        _replace_panel,
        html,
        flags=re.DOTALL,
    )

    # Jira issue embeds: <span class="jira-issue" data-jira-key="KEY"> → {jira:KEY}
    # Use greedy match to consume nested spans (e.g. <span class="summary">)
    html = re.sub(
        r'<span[^>]*class="jira-issue"[^>]*data-jira-key="([^"]*)"[^>]*>.*?</span>\s*</span>',
        r"{jira:\1}",
        html,
        flags=re.DOTALL,
    )

    # Generic panel macro: <div class="panel"...><div class="panelHeader">TITLE</div><div class="panelContent">BODY</div></div>
    def _replace_generic_panel(m):
        title_html = m.group(1) or ""
        body_html = m.group(2)
        title = re.sub(r'<[^>]+>', '', title_html).strip()
        body = re.sub(r'<[^>]+>', '', body_html).strip()
        header = f"{{panel:panel|{title}}}" if title else "{panel:panel}"
        return f"PANEL-START: {header}<br/>PANEL-BODY: {body}<br/>PANEL-END"

    html = re.sub(
        r'<div[^>]*class="panel"[^>]*>'
        r'(?:<div[^>]*class="panelHeader"[^>]*>(.*?)</div>)?'
        r'\s*<div[^>]*class="panelContent"[^>]*>(.*?)</div>\s*</div>',
        _replace_generic_panel,
        html,
        flags=re.DOTALL,
    )

    # Colspan header rows: <th colspan="N">TEXT</th> → || TEXT || marker
    html = re.sub(
        r'<tr[^>]*>\s*<th[^>]*colspan="(\d+)"[^>]*>(.*?)</th>\s*</tr>',
        lambda m: f'<tr><td>|| {m.group(2).strip()} ||</td></tr>',
        html,
    )

    # Last, after all cell-content rewrites: guard empty cells against html2text.
    html = _fill_empty_table_cells(html)

    return html


def _restore_empty_table_cells(md_text):
    """Strip the empty-cell sentinel, re-emitting each affected row with explicit edge
    pipes so an empty leading/trailing cell survives GFM re-parsing (a bare-space cell at
    a row edge would be re-collapsed). Column counts are preserved because the sentinel
    kept every cell present through html2text.
    """
    out = []
    for line in md_text.split("\n"):
        if EMPTY_CELL_SENTINEL not in line:
            out.append(line)
            continue
        body = line.rstrip()
        trailing = line[len(body):]           # keep html2text's row-terminating spaces
        body = body.strip()
        if body.startswith("|"):
            body = body[1:]
        if body.endswith("|"):
            body = body[:-1]
        cells = [c.strip().replace(EMPTY_CELL_SENTINEL, "") for c in body.split("|")]
        out.append("| " + " | ".join(cells) + " |" + trailing)
    return "\n".join(out)


def postprocess_export_md(md_text):
    """Convert placeholders back to markdown syntax after html2text."""
    if EMPTY_CELL_SENTINEL in md_text:
        md_text = _restore_empty_table_cells(md_text)
    md_text = re.sub(r'TASK-CHECKED: (.+)', r'- [x] \1', md_text)
    md_text = re.sub(r'TASK-UNCHECKED: (.+)', r'- [ ] \1', md_text)

    # Panel placeholders → blockquote syntax
    def _restore_panel(m):
        header = m.group(1).strip()
        body = m.group(2).strip()
        lines = [f"> {header}"]
        for line in body.split("\n"):
            lines.append(f"> {line.strip()}")
        return "\n".join(lines)

    md_text = re.sub(
        r'PANEL-START: (.+?)[\s]*PANEL-BODY: (.+?)[\s]*PANEL-END',
        _restore_panel,
        md_text,
        flags=re.DOTALL,
    )

    # Expand placeholders → <details> syntax
    def _restore_expand(m):
        title = m.group(1).strip()
        body = m.group(2).strip()
        return f"<details>\n<summary>{title}</summary>\n\n{body}\n\n</details>"

    md_text = re.sub(
        r'EXPAND-START: (.+?)[\s]*EXPAND-BODY: (.+?)[\s]*EXPAND-END',
        _restore_expand,
        md_text,
        flags=re.DOTALL,
    )

    return md_text


def find_details_ids(storage_html):
    """Return the `id` parameter of each Page Properties (details) macro, in document order."""
    ids = []
    for m in re.finditer(r'<ac:structured-macro ac:name="details"', storage_html):
        start = m.start()
        rtb = storage_html.find("<ac:rich-text-body", start)
        prefix = storage_html[start:rtb] if rtb != -1 else storage_html[start:start + 400]
        id_match = re.search(r'<ac:parameter ac:name="id">([^<]*)</ac:parameter>', prefix)
        ids.append(id_match.group(1) if id_match else None)
    return ids


def _compact_inline_html(inner_html):
    """Collapse block cell content (e.g. a list) into single-line inline HTML."""
    soup = BeautifulSoup(inner_html, "html.parser")
    for tag in soup.find_all(["div", "p"]):
        tag.unwrap()
    for tag in soup.find_all(True):
        if tag.name == "a" and tag.get("href"):
            tag.attrs = {"href": tag["href"]}
        else:
            tag.attrs = {}
    return re.sub(r"\s+", " ", str(soup)).strip()


def _export_cell_to_md(cell):
    """Render a details-macro table cell (BeautifulSoup tag) to inline markdown."""
    inner = convert_inline_confluence_tokens(cell.decode_contents())
    if re.search(r"<(ol|ul|table)\b", inner):
        return _compact_inline_html(inner)
    h = html2text.HTML2Text()
    h.body_width = 0
    h.ignore_links = False
    h.ignore_images = False
    return re.sub(r"\s+", " ", h.handle(inner).strip())


def _details_div_to_markdown(div, macro_id):
    """Convert a rendered plugin-tabmeta-details div into a page-properties markdown block."""
    table = div.find("table")
    rows = []
    if table is not None:
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if cells:
                rows.append([_export_cell_to_md(c) for c in cells])
    ncols = max((len(r) for r in rows), default=2)
    if ncols <= 2:
        head = ["Property", "Value"][:ncols] or ["Property"]
    else:
        head = [f"Column {i + 1}" for i in range(ncols)]
    directive = f"<!-- page-properties id={macro_id} -->" if macro_id else "<!-- page-properties -->"
    lines = [
        directive,
        "| " + " | ".join(head) + " |",
        "| " + " | ".join(["---"] * ncols) + " |",
    ]
    for row in rows:
        padded = row + [""] * (ncols - len(row))
        lines.append("| " + " | ".join(padded) + " |")
    return "\n".join(lines)


def extract_page_property_divs(export_html, storage_html):
    """Replace rendered Page Properties divs with tokens; return (html, {token: md block})."""
    ids = find_details_ids(storage_html)
    soup = BeautifulSoup(export_html, "html.parser")
    divs = soup.find_all("div", class_="plugin-tabmeta-details")
    if not divs:
        return export_html, {}
    mapping = {}
    for idx, div in enumerate(divs):
        macro_id = ids[idx] if idx < len(ids) else None
        token = f"PAGEPROPSEXPORT{idx}"
        mapping[token] = _details_div_to_markdown(div, macro_id)
        placeholder = soup.new_tag("p")
        placeholder.string = token
        div.replace_with(placeholder)
    return str(soup), mapping


def find_report_params(storage_html):
    """Return the parameters of each detailssummary macro, in document order."""
    result = []
    for m in re.finditer(
        r'<ac:(?:structured-)?macro ac:name="detailssummary".*?</ac:(?:structured-)?macro>',
        storage_html,
        re.DOTALL,
    ):
        params = re.findall(r'<ac:parameter ac:name="([^"]+)">([^<]*)</ac:parameter>', m.group(0))
        result.append([(k, v) for k, v in params])
    return result


def _report_directive(params):
    parts = [f'{k}="{v}"' if " " in v else f"{k}={v}" for k, v in params]
    inner = (" " + " ".join(parts)) if parts else ""
    return f"<!-- page-properties-report{inner} -->"


def extract_report_macros(export_html, storage_html):
    """Replace rendered Page Properties Report tables with directive tokens."""
    params_list = find_report_params(storage_html)
    soup = BeautifulSoup(export_html, "html.parser")
    tables = soup.find_all("table", class_="metadata-summary-macro")
    if not tables:
        return export_html, {}
    mapping = {}
    for idx, table in enumerate(tables):
        params = params_list[idx] if idx < len(params_list) else []
        token = f"PAGEPROPSREPORT{idx}"
        mapping[token] = _report_directive(params)
        placeholder = soup.new_tag("p")
        placeholder.string = token
        table.replace_with(placeholder)
    return str(soup), mapping


def _find_top_level_tables(storage_html):
    """Return verbatim `<table>…</table>` XML for top-level tables in document order.

    "Top-level" means not nested inside another `<table>` and not inside an
    `<ac:structured-macro>` / `<ac:macro>` (those are macro-rendered and handled by
    the dedicated passthrough / page-property paths). Returns the raw storage
    substrings so the tables can be preserved byte-for-byte.
    """
    open_tag = "<table"
    close_tag = "</table>"
    macro_open = re.compile(r"<ac:(?:structured-)?macro\b")
    macro_close = "</ac:macro>"
    macro_struct_close = "</ac:structured-macro>"

    def _inside_macro(idx):
        """True if position idx sits inside an unclosed ac:(structured-)macro."""
        depth = 0
        for m in re.finditer(
            r"<ac:(?:structured-)?macro\b|</ac:structured-macro>|</ac:macro>",
            storage_html[:idx],
        ):
            depth += 1 if m.group(0).startswith("<ac:") else -1
        return depth > 0

    results = []
    pos = 0
    while True:
        start = storage_html.find(open_tag, pos)
        if start == -1:
            break
        # Ensure it's actually a <table ...> / <table> tag, not <tablefoo>.
        after = storage_html[start + len(open_tag): start + len(open_tag) + 1]
        if after not in (">", " ", "\t", "\n", "\r", "/"):
            pos = start + len(open_tag)
            continue
        end = storage_html.find(close_tag, start)
        if end == -1:
            break
        end += len(close_tag)
        # Handle nested tables: count opens vs closes within [start, end).
        while storage_html.count(open_tag, start, end) > storage_html.count(close_tag, start, end):
            nxt = storage_html.find(close_tag, end)
            if nxt == -1:  # pragma: no cover
                break
            end = nxt + len(close_tag)
        if not _inside_macro(start):
            results.append(storage_html[start:end])
        pos = end
    return results


_BLOCK_CELL_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table"}


def _cell_is_unsafe(cell):
    """True if a rendered `<td>`/`<th>` cannot be represented in a single GFM line.

    Unsafe = contains a heading, list, or nested table; has multiple block-level
    children; or embeds a non-inline macro. An inline status lozenge
    (`<span class="status-macro">`) alone is safe and stays editable.
    """
    for tag in cell.find_all(True):
        if tag.name in _BLOCK_CELL_TAGS:
            return True
    # Multiple block-level (<p>/<div>) children indicate multi-paragraph content
    # that html2text would spread across several lines.
    block_children = [c for c in cell.find_all(["p", "div"], recursive=True)]
    if len(block_children) > 1:
        return True
    return False


def extract_unsafe_tables(export_html, storage_html, start_counter=0):
    """Preserve tables with block-content cells verbatim via the passthrough footer.

    Such tables render across multiple lines through html2text, producing
    GFM-invalid markdown that Python-Markdown then re-parses lossily (leaking cell
    content out of the table). Instead of round-tripping them, we swap each unsafe
    table in the export-view HTML for a passthrough placeholder paragraph and store
    the ORIGINAL storage-format `<table>` XML so it is restored byte-for-byte.

    Export-view tables are matched to storage tables by document order among
    top-level tables. Report/page-property tables are removed from the export view
    before this runs, so the remainder correspond 1:1. If the counts don't line up
    we refuse to guess and leave every table unconverted.

    Returns (new_export_html, {marker: verbatim_storage_xml}).
    """
    soup = BeautifulSoup(export_html, "html.parser")
    export_tables = [t for t in soup.find_all("table") if t.find_parent("table") is None]
    if not export_tables:
        return export_html, {}

    storage_tables = _find_top_level_tables(storage_html)
    if len(storage_tables) != len(export_tables):
        # Counts don't line up: never pass through the wrong XML. Leave unconverted.
        return export_html, {}

    mapping = {}
    counter = start_counter
    for export_table, storage_xml in zip(export_tables, storage_tables):
        cells = export_table.find_all(["td", "th"])
        if not any(_cell_is_unsafe(c) for c in cells):
            continue  # simple table: keep editable markdown behavior unchanged
        marker = f"{PASSTHROUGH_PREFIX}{counter}"
        counter += 1
        mapping[marker] = storage_xml
        placeholder = soup.new_tag("p")
        placeholder.string = marker
        export_table.replace_with(placeholder)

    if not mapping:
        return export_html, {}
    return str(soup), mapping


def unescape_html(text):
    """Unescape HTML entities inside code blocks for CDATA."""
    return (text
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"'))


def _escape_cdata(text):
    """Escape ']]>' sequences so they don't terminate a wrapping CDATA section."""
    return text.replace("]]>", "]]]]><![CDATA[>")


def rewrite_local_images(html, base_dir):
    """Replace local <img> tags with Confluence <ac:image><ri:attachment> references.

    Returns (rewritten_html, [(filename, abs_path), ...]) where the list contains
    attachments the caller must upload to the page. External URLs, data: URIs,
    and missing files are left untouched.
    """
    images = []
    seen = set()

    def _rewrite(m):
        tag = m.group(0)
        src_match = re.search(r'src="([^"]+)"', tag)
        if not src_match:
            return tag
        src = src_match.group(1)
        if src.startswith(("http://", "https://", "//", "data:", "/")):
            return tag
        abs_path = os.path.normpath(os.path.join(base_dir, src))
        if not os.path.isfile(abs_path):
            return tag
        filename = os.path.basename(src)
        if filename not in seen:
            images.append((filename, abs_path))
            seen.add(filename)
        alt_match = re.search(r'alt="([^"]*)"', tag)
        alt_attr = f' ac:alt="{alt_match.group(1)}"' if alt_match and alt_match.group(1) else ""
        return f'<ac:image{alt_attr}><ri:attachment ri:filename="{filename}" /></ac:image>'

    html = re.sub(r'<img\b[^>]*/?>', _rewrite, html)
    return html, images


ATTACHMENT_URL_MARKERS = ("/download/attachments/", "/download/thumbnails/")


def rewrite_attachment_images(html):
    """Point <img> tags at bare attachment filenames instead of server URLs.

    Returns (rewritten_html, [filename, ...]) so the caller can fetch the files
    that the markdown now expects to sit beside it. Matching is on the URL
    marker rather than by correlating <img> order against storage
    <ri:attachment> elements: export_view renders emoticons as <img> too, and
    one interleaved emoticon would shift every later pairing.
    """
    names = []

    def _rewrite(m):
        tag = m.group(0)
        src_match = re.search(r'src="([^"]+)"', tag)
        if not src_match:
            return tag
        path = urlsplit(src_match.group(1)).path
        if not any(marker in path for marker in ATTACHMENT_URL_MARKERS):
            return tag
        filename = unquote(os.path.basename(path))
        if not filename:
            return tag
        if filename not in names:
            names.append(filename)
        return tag.replace(src_match.group(0), f'src="{filename}"')

    return re.sub(r'<img\b[^>]*/?>', _rewrite, html), names


def parse_directive_params(param_str):
    """Parse `key=value key="quoted value"` pairs from a directive into an ordered list."""
    pairs = []
    for m in re.finditer(r'([\w-]+)=(?:"([^"]*)"|(\S+))', param_str):
        value = m.group(2) if m.group(2) is not None else m.group(3)
        pairs.append((m.group(1), value))
    return pairs


def _parse_page_property_rows(table_text):
    """Parse a markdown table body into rows of cells, dropping separators and the header row."""
    rows = []
    for line in table_text.splitlines():
        line = line.strip()
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.split("|")]
        if cells and cells[0] == "":
            cells = cells[1:]
        if cells and cells[-1] == "":
            cells = cells[:-1]
        if not cells:
            continue
        if all(re.fullmatch(r":?-+:?", c) for c in cells):
            continue  # separator row
        rows.append(cells)
    # First non-separator row is the cosmetic header; discard it.
    return rows[1:] if rows else []


def _page_property_cell(cell):
    """Render a single table cell to inline Confluence content.

    Block HTML (e.g. an inline `<ol>` list) passes through untouched; simple text
    is run through the markdown parser and unwrapped from its enclosing paragraph.
    """
    html = md_lib.markdown(cell, extensions=MD_EXTENSIONS).strip()
    m = re.match(r"^<p>(.*)</p>$", html, re.DOTALL)
    if m:
        html = m.group(1)
    return html


def _build_details_macro(macro_id, rows):
    """Build a Confluence `details` (Page Properties) macro from parsed table rows."""
    trs = []
    for cells in rows:
        if not cells:
            continue
        parts = [f"<th>{_page_property_cell(cells[0])}</th>"]
        parts.extend(f"<td>{_page_property_cell(c)}</td>" for c in cells[1:])
        trs.append("<tr>" + "".join(parts) + "</tr>")
    id_param = f'<ac:parameter ac:name="id">{macro_id}</ac:parameter>' if macro_id else ""
    return (
        f'<ac:structured-macro ac:name="details" ac:schema-version="1">'
        f"{id_param}<ac:rich-text-body><table><tbody>"
        f'{"".join(trs)}</tbody></table></ac:rich-text-body></ac:structured-macro>'
    )


def extract_page_properties(md_text):
    """Replace page-properties directive blocks with placeholders; return (text, mapping)."""
    blocks = {}
    counter = [0]

    def _extract(m):
        rows = _parse_page_property_rows(m.group("table"))
        key = f"PAGEPROPSBLOCK{counter[0]}"
        blocks[key] = (m.group("id"), rows)
        counter[0] += 1
        return key

    md_text = re.sub(
        r"<!-- ?page-properties(?!-report)(?: +id=(?P<id>\S+?))? ?-->[ \t]*\n"
        r"(?P<table>(?:[ \t]*\|.*\n?)+)",
        _extract,
        md_text,
    )
    return md_text, blocks


_VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

_TAG_TOKEN_RE = re.compile(
    r'<!--.*?-->'
    r'|<!\[CDATA\[.*?\]\]>'
    r'|<(?P<close>/)?(?P<name>[a-zA-Z][\w:.-]*)\b[^<>]*?(?P<selfclose>/)?>',
    re.DOTALL,
)


def _escape_unmatched_tags(html):
    """Escape `<...>` tokens with no matching open/close partner anywhere in the
    document — e.g. a literal `<table>` used as a placeholder in prose. Left alone,
    Python-Markdown's raw-HTML passthrough treats it as a real, unclosed tag, and
    everything after it is parsed as if nested inside that element — corrupting the
    rest of the generated document (surfaces as an XML parse error on upload:
    "Unexpected close tag ...; expected </table>").

    Runs on HTML already produced by md_lib.markdown() (including the nested calls
    used to render panel/expand/page-property bodies), not the raw markdown source:
    by this point real code (fenced/inline/indented) has already had its contents
    HTML-escaped by the markdown parser itself, so there is no need to re-derive
    "is this inside code" here — genuine code content has no literal unescaped
    `<`/`>` left to match against, and a real autolink like `<https://x>` has
    already become a proper `<a href="...">` pair.

    Matching is a simple per-tag-name stack, not a full parser — cheap, and enough
    to catch genuinely orphaned tokens without special-casing every tag this module
    happens to emit elsewhere (ac:*, ri:*, iframe, br, ...), since a well-formed
    pair is never flagged regardless of its name. Known limitation: two
    independently-mismatched tags of different names that happen to interleave
    (`<table>...<div>...</table>...</div>`) won't be caught — real breakage there
    surfaces downstream instead.
    """
    tokens = []
    for m in _TAG_TOKEN_RE.finditer(html):
        name = m.group("name")
        if name is None:  # comment / CDATA — always self-contained
            continue
        name = name.lower()
        if name in _VOID_ELEMENTS or m.group("selfclose"):
            continue
        tokens.append((m.start(), m.end(), name, m.group("close") is not None))

    stacks = defaultdict(list)
    unmatched = set()
    for idx, (_start, _end, name, is_close) in enumerate(tokens):
        if is_close:
            if stacks[name]:
                stacks[name].pop()
            else:
                unmatched.add(idx)  # stray closing tag
        else:
            stacks[name].append(idx)
    for stack in stacks.values():
        unmatched.update(stack)  # opens left on the stack are unmatched

    if not unmatched:
        return html

    out = html
    for idx in sorted(unmatched, reverse=True):  # right to left: offsets stay valid
        start, end, _name, _is_close = tokens[idx]
        out = out[:start] + "&lt;" + html[start + 1:end - 1] + "&gt;" + out[end:]
    return out


def md_to_confluence_html(md_text):
    """Convert markdown to Confluence storage format HTML."""
    # Extract passthrough blocks first
    md_text, passthrough_mapping = extract_passthrough_footer(md_text)

    def _replace_status_md(m):
        title = m.group(1)
        colour = COLOUR_TO_CONFLUENCE.get(m.group(2).lower(), "Grey")
        return (
            f'<ac:structured-macro ac:name="status">'
            f'<ac:parameter ac:name="colour">{colour}</ac:parameter>'
            f'<ac:parameter ac:name="title">{title}</ac:parameter>'
            f'</ac:structured-macro>'
        )

    md_text = re.sub(r'\{status:([^|]+)\|([^}]+)\}', _replace_status_md, md_text)

    # Convert {jira:KEY} to Confluence Jira issue macro
    md_text = re.sub(
        r'\{jira:([A-Z]+-\d+)\}',
        r'<ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">\1</ac:parameter></ac:structured-macro>',
        md_text,
    )

    # Convert {date:YYYY-MM-DD} to Confluence date element
    md_text = re.sub(
        r'\{date:(\d{4}-\d{2}-\d{2})\}',
        r'<time datetime="\1" />',
        md_text,
    )

    # Extract <details> blocks before markdown parsing
    expand_blocks = {}
    expand_counter = [0]

    def _extract_details(m):
        title = m.group(1).strip()
        body = m.group(2).strip()
        key = f"EXPAND-BLOCK-{expand_counter[0]}"
        expand_blocks[key] = (title, body)
        expand_counter[0] += 1
        return key

    md_text = re.sub(
        r'<details>\s*<summary>(.*?)</summary>(.*?)</details>',
        _extract_details,
        md_text,
        flags=re.DOTALL,
    )

    # Extract panel blocks before markdown parsing (to avoid md parser wrapping XML in <p> tags).
    # Store as placeholders, convert to XML after markdown parsing.
    panel_blocks = {}
    panel_counter = [0]

    def _extract_panel_block(m):
        block = m.group(0)
        header_match = re.match(r'> \{panel:(\w+)(?:\|([^}]*))?\}', block)
        if not header_match:  # pragma: no cover
            return block
        panel_type = header_match.group(1)
        title = header_match.group(2) or ""
        body_lines = []
        for line in block.split("\n")[1:]:
            body_lines.append(re.sub(r'^> ?', '', line))
        body = "\n".join(body_lines).strip()
        key = f"PANEL-BLOCK-{panel_counter[0]}"
        panel_blocks[key] = (panel_type, title, body)
        panel_counter[0] += 1
        return key

    md_text = re.sub(r'^> \{panel:\w+(?:\|[^}]*)?\}(?:\n>[ ]?.*)*', _extract_panel_block, md_text, flags=re.MULTILINE)

    # Convert markdown checkboxes to Confluence task list
    def _convert_md_tasks(m):
        block = m.group(0)
        tasks = []
        for i, task_match in enumerate(re.finditer(r'- \[([ xX])\] (.+)', block)):
            checked = task_match.group(1).lower() == "x"
            text = task_match.group(2)
            status = "complete" if checked else "incomplete"
            tasks.append(
                f'<ac:task><ac:task-id>{i + 1}</ac:task-id>'
                f'<ac:task-status>{status}</ac:task-status>'
                f'<ac:task-body><span>{text}</span></ac:task-body>'
                f'</ac:task>'
            )
        return f'<ac:task-list>{"".join(tasks)}</ac:task-list>'

    md_text = re.sub(r'(?:^- \[[ xX]\] .+\n?)+', _convert_md_tasks, md_text, flags=re.MULTILINE)

    # Convert @username mentions to Confluence user links, but never inside code
    # regions: an inline span like `@modelcontextprotocol/sdk` or a fenced block
    # with a `@decorator` is code, not a mention. The combined pattern matches
    # code regions first and returns them unchanged, so the mention branch only
    # fires in prose. The `(?![\w/])` lookahead also skips scoped-package refs
    # (`@scope/pkg`) that appear outside code. The `@` added to the lookbehind
    # class skips the second `@` of a `@@TEMPLATE_TOKEN@@` placeholder (e.g.
    # `@@DEST_DATASET@@` in dbt SQL examples) — without it, that second `@` reads
    # as a bare mention and gets rewritten into a link for a nonexistent user.
    def _convert_mention(m):
        if m.group("user"):
            return f'<ac:link><ri:user ri:username="{m.group("user")}" /></ac:link>'
        return m.group(0)

    md_text = re.sub(
        r'(?P<fence>```.*?```|~~~.*?~~~)'        # fenced code blocks
        r'|(?P<inline>`+[^`]*`+)'                # inline code spans
        r'|(?<!["\w@])@(?P<user>\w+)(?![\w/])',  # user mention (not in code, not scoped pkg)
        _convert_mention,
        md_text,
        flags=re.DOTALL,
    )

    # Extract page-properties blocks before parsing (inline tokens above are already
    # converted, so cell values carry their status/user/date/jira XML).
    md_text, page_property_blocks = extract_page_properties(md_text)

    # Extract colspan rows from markdown tables before parsing.
    # || TEXT || rows become placeholders that survive markdown table parsing.
    colspan_rows = {}
    colspan_counter = [0]

    def _extract_colspan(m):
        text = m.group(1).strip()
        key = f"COLSPAN-MARKER-{colspan_counter[0]}__"
        colspan_rows[key] = text
        colspan_counter[0] += 1
        # Return a normal-looking table row with the placeholder in the first cell
        return f"| {key} |"

    md_text = re.sub(r'^\|\| (.+?) \|\|.*$', _extract_colspan, md_text, flags=re.MULTILINE)

    html = md_lib.markdown(md_text, extensions=MD_EXTENSIONS)

    # Replace colspan placeholders with actual colspan th elements.
    # Count columns from the table's thead to determine the span width.
    for key, text in colspan_rows.items():
        # Find the row containing the placeholder (may have empty cells before it)
        row_pattern = re.compile(
            r'<tr>(?:\s*<td></td>)*\s*<td>' + re.escape(key) + r'</td>(?:\s*<td></td>)*\s*</tr>'
        )
        row_match = row_pattern.search(html)
        if row_match:
            pos = row_match.start()
            # Find the nearest thead before this position to count columns
            thead_start = html.rfind("<thead>", 0, pos)
            col_count = 1
            if thead_start != -1:
                thead_end = html.find("</thead>", thead_start)
                thead_html = html[thead_start:thead_end] if thead_end != -1 else ""
                col_count = thead_html.count("<th>") + len(re.findall(r"<th ", thead_html))
            html = row_pattern.sub(
                f'<tr><th colspan="{col_count}">{text}</th></tr>',
                html,
                count=1,
            )

    html = re.sub(
        r'<pre><code class="language-(\w+)">(.*?)</code></pre>',
        lambda m: (
            f'<ac:structured-macro ac:name="code">'
            f'<ac:parameter ac:name="language">{m.group(1)}</ac:parameter>'
            f'<ac:plain-text-body><![CDATA[{_escape_cdata(unescape_html(m.group(2)))}]]></ac:plain-text-body>'
            f'</ac:structured-macro>'
        ),
        html,
        flags=re.DOTALL,
    )
    html = re.sub(
        r'<pre><code>(.*?)</code></pre>',
        lambda m: (
            f'<ac:structured-macro ac:name="code">'
            f'<ac:plain-text-body><![CDATA[{_escape_cdata(unescape_html(m.group(1)))}]]></ac:plain-text-body>'
            f'</ac:structured-macro>'
        ),
        html,
        flags=re.DOTALL,
    )

    # [TOC] → Confluence table of contents macro
    html = re.sub(
        r'<p>\[TOC\]</p>',
        '<p><ac:structured-macro ac:name="toc" ac:schema-version="1" /></p>',
        html,
    )

    # <iframe>…</iframe> → Confluence HTML macro (preserves iframe raw)
    html = re.sub(
        r'<iframe\b[^>]*>.*?</iframe>',
        lambda m: (
            f'<ac:structured-macro ac:name="html">'
            f'<ac:plain-text-body><![CDATA[{_escape_cdata(m.group(0))}]]></ac:plain-text-body>'
            f'</ac:structured-macro>'
        ),
        html,
        flags=re.DOTALL,
    )

    # Restore panel block placeholders with actual XML (after markdown parsing)
    for key, (panel_type, title, body) in panel_blocks.items():
        body_html = md_lib.markdown(body, extensions=MD_EXTENSIONS)
        title_param = f'<ac:parameter ac:name="title">{title}</ac:parameter>' if title else ""
        panel_xml = (
            f'<ac:structured-macro ac:name="{panel_type}">'
            f'{title_param}'
            f'<ac:rich-text-body>{body_html}</ac:rich-text-body>'
            f'</ac:structured-macro>'
        )
        html = html.replace(f"<p>{key}</p>", panel_xml)
        html = html.replace(key, panel_xml)

    # Restore expand block placeholders with actual XML
    for key, (title, body) in expand_blocks.items():
        body_html = md_lib.markdown(body, extensions=MD_EXTENSIONS) if body else ""
        expand_xml = (
            f'<ac:structured-macro ac:name="expand">'
            f'<ac:parameter ac:name="title">{title}</ac:parameter>'
            f'<ac:rich-text-body>{body_html}</ac:rich-text-body>'
            f'</ac:structured-macro>'
        )
        html = html.replace(f"<p>{key}</p>", expand_xml)
        html = html.replace(key, expand_xml)

    # Page Properties Report directive -> detailssummary macro. Done after the
    # markdown parse because python-markdown preserves HTML comments verbatim
    # (so the macro is not wrapped in a <p> tag).
    def _replace_report(m):
        params = parse_directive_params(m.group(1))
        param_xml = "".join(
            f'<ac:parameter ac:name="{k}">{v}</ac:parameter>' for k, v in params
        )
        return (
            f'<ac:structured-macro ac:name="detailssummary" ac:schema-version="1">'
            f'{param_xml}</ac:structured-macro>'
        )

    html = re.sub(
        r'<!-- ?page-properties-report +([^>]*?) ?-->',
        _replace_report,
        html,
    )

    # Restore page-properties block placeholders with the details macro XML
    for key, (macro_id, rows) in page_property_blocks.items():
        macro = _build_details_macro(macro_id, rows)
        html = html.replace(f"<p>{key}</p>", macro)
        html = html.replace(key, macro)

    # Escape any tag-like token still unmatched now that panel/expand/page-property
    # bodies (each parsed by their own nested md_lib.markdown() call above) are
    # spliced in. Must run before passthrough restoration: passthrough XML is
    # verbatim, already-valid storage markup and must never be touched by this.
    html = _escape_unmatched_tags(html)

    # Restore passthrough blocks
    html = restore_passthrough_blocks(html, passthrough_mapping)

    return html


def strip_frontmatter_and_title(md_text):
    """Strip YAML frontmatter and title heading, return (title, body)."""
    fm_match = re.match(r"^---\n.*?\n---\n\n?", md_text, re.DOTALL)
    if fm_match:
        md_text = md_text[fm_match.end():]

    title = None
    title_match = re.match(r"^# (.+)\n\n", md_text)
    if title_match:
        title = title_match.group(1).strip()
        md_text = md_text[title_match.end():]

    return title, md_text
