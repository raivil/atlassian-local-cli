import re

import markdown as md_lib

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


def preprocess_export_html(html):
    """Convert Confluence-specific HTML elements to markdown-friendly tokens before html2text."""

    def _replace_status(m):
        classes = m.group(1)
        title = m.group(2)
        colour = "grey"
        for cls, col in LOZENGE_TO_COLOUR.items():
            if cls in classes:
                colour = col
                break
        return f"{{status:{title}|{colour}}}"

    html = re.sub(
        r'<span[^>]*class="(status-macro[^"]*)"[^>]*>([^<]*)</span>',
        _replace_status,
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

    return html


def postprocess_export_md(md_text):
    """Convert placeholders back to markdown syntax after html2text."""
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

    return md_text


def unescape_html(text):
    """Unescape HTML entities inside code blocks for CDATA."""
    return (text
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"'))


def md_to_confluence_html(md_text):
    """Convert markdown to Confluence storage format HTML."""

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

    # Convert panel blocks: > {panel:type|title}\n> content
    def _convert_panel_block(m):
        block = m.group(0)
        # Extract header line
        header_match = re.match(r'> \{panel:(\w+)(?:\|([^}]*))?\}', block)
        if not header_match:  # pragma: no cover
            return block
        panel_type = header_match.group(1)
        title = header_match.group(2) or ""
        # Extract body lines (everything after the header)
        body_lines = []
        for line in block.split("\n")[1:]:
            body_lines.append(re.sub(r'^> ?', '', line))
        body = "\n".join(body_lines).strip()
        body_html = md_lib.markdown(body, extensions=["tables", "fenced_code"])
        title_param = f'<ac:parameter ac:name="title">{title}</ac:parameter>' if title else ""
        return (
            f'<ac:structured-macro ac:name="{panel_type}">'
            f'{title_param}'
            f'<ac:rich-text-body>{body_html}</ac:rich-text-body>'
            f'</ac:structured-macro>'
        )

    md_text = re.sub(r'^> \{panel:\w+(?:\|[^}]*)?\}(?:\n> .*)*', _convert_panel_block, md_text, flags=re.MULTILINE)

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

    md_text = re.sub(
        r'(?<!["\w])@(\w+)(?!\w)',
        r'<ac:link><ri:user ri:username="\1" /></ac:link>',
        md_text,
    )

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

    html = md_lib.markdown(md_text, extensions=["tables", "fenced_code"])

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
            f'<ac:plain-text-body><![CDATA[{unescape_html(m.group(2))}]]></ac:plain-text-body>'
            f'</ac:structured-macro>'
        ),
        html,
        flags=re.DOTALL,
    )
    html = re.sub(
        r'<pre><code>(.*?)</code></pre>',
        lambda m: (
            f'<ac:structured-macro ac:name="code">'
            f'<ac:plain-text-body><![CDATA[{unescape_html(m.group(1))}]]></ac:plain-text-body>'
            f'</ac:structured-macro>'
        ),
        html,
        flags=re.DOTALL,
    )
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
