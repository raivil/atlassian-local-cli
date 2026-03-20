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

    # Colspan header rows: <th colspan="N">TEXT</th> → || TEXT || marker
    html = re.sub(
        r'<tr[^>]*>\s*<th[^>]*colspan="(\d+)"[^>]*>(.*?)</th>\s*</tr>',
        lambda m: f'<tr><td>|| {m.group(2).strip()} ||</td></tr>',
        html,
    )

    return html


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
        # Find the row containing the placeholder
        row_pattern = re.compile(
            r'<tr>\s*<td>' + re.escape(key) + r'</td>(?:\s*<td></td>)*\s*</tr>'
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
