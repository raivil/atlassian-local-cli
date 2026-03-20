from atlassian_local_cli.converters import (
    md_to_confluence_html,
    preprocess_export_html,
    strip_frontmatter_and_title,
    unescape_html,
)


class TestPreprocessExportHtml:
    def test_status_badge_success(self):
        html = '<span class="status-macro aui-lozenge aui-lozenge-success">DONE</span>'
        assert preprocess_export_html(html) == "{status:DONE|green}"

    def test_status_badge_error(self):
        html = '<span class="status-macro aui-lozenge aui-lozenge-error">FAILED</span>'
        assert preprocess_export_html(html) == "{status:FAILED|red}"

    def test_status_badge_current(self):
        html = '<span class="status-macro aui-lozenge aui-lozenge-current">IN PROGRESS</span>'
        assert preprocess_export_html(html) == "{status:IN PROGRESS|blue}"

    def test_status_badge_moved(self):
        html = '<span class="status-macro aui-lozenge aui-lozenge-moved">PENDING</span>'
        assert preprocess_export_html(html) == "{status:PENDING|yellow}"

    def test_status_badge_default_grey(self):
        html = '<span class="status-macro aui-lozenge">NOT STARTED</span>'
        assert preprocess_export_html(html) == "{status:NOT STARTED|grey}"

    def test_user_mention(self):
        html = '<a class="confluence-userlink user-mention" data-username="jdoe" href="/display/~jdoe">John Doe</a>'
        assert preprocess_export_html(html) == "@jdoe"

    def test_multiple_elements(self):
        html = (
            '<span class="status-macro aui-lozenge aui-lozenge-success">OK</span> '
            '<a class="confluence-userlink user-mention" data-username="alice" href="#">Alice</a>'
        )
        result = preprocess_export_html(html)
        assert "{status:OK|green}" in result
        assert "@alice" in result

    def test_plain_html_passthrough(self):
        html = "<p>Hello <strong>world</strong></p>"
        assert preprocess_export_html(html) == html


class TestUnescapeHtml:
    def test_all_entities(self):
        assert unescape_html("&amp; &lt; &gt; &quot;") == '& < > "'

    def test_no_entities(self):
        assert unescape_html("plain text") == "plain text"


class TestMdToConfluenceHtml:
    def test_status_badge(self):
        result = md_to_confluence_html("{status:DONE|green}")
        assert 'ac:name="status"' in result
        assert 'ac:name="colour">Green<' in result
        assert 'ac:name="title">DONE<' in result

    def test_status_badge_in_table(self):
        md = "| Col |\n|---|\n| {status:OK|green} |"
        result = md_to_confluence_html(md)
        assert 'ac:name="status"' in result
        assert "<td>" in result

    def test_status_badge_unknown_colour_defaults_grey(self):
        result = md_to_confluence_html("{status:TODO|purple}")
        assert "Grey" in result

    def test_user_mention(self):
        result = md_to_confluence_html("Assigned to @jdoe for review.")
        assert 'ri:username="jdoe"' in result

    def test_user_mention_not_in_email(self):
        result = md_to_confluence_html("Email user@example.com")
        assert "ri:username" not in result

    def test_fenced_code_with_language(self):
        md = "```python\nprint('hi')\n```"
        result = md_to_confluence_html(md)
        assert 'ac:name="code"' in result
        assert 'ac:name="language">python<' in result
        assert "CDATA[print('hi')" in result

    def test_fenced_code_no_language(self):
        md = "```\nsome code\n```"
        result = md_to_confluence_html(md)
        assert 'ac:name="code"' in result
        assert "CDATA[some code" in result

    def test_code_block_unescapes_entities(self):
        md = "```python\nif a < b & c > d:\n```"
        result = md_to_confluence_html(md)
        assert "CDATA[if a < b & c > d:" in result

    def test_table(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = md_to_confluence_html(md)
        assert "<table>" in result
        assert "<td>1</td>" in result

    def test_combined(self):
        md = "@alice {status:OK|green}\n\n```bash\necho hi\n```"
        result = md_to_confluence_html(md)
        assert "ri:username" in result
        assert 'ac:name="status"' in result
        assert 'ac:name="code"' in result


class TestStripFrontmatterAndTitle:
    def test_frontmatter_only(self):
        md = "---\nkey: val\n---\n\nbody text"
        title, body = strip_frontmatter_and_title(md)
        assert title is None
        assert body == "body text"

    def test_title_only(self):
        md = "# My Title\n\nbody text"
        title, body = strip_frontmatter_and_title(md)
        assert title == "My Title"
        assert body == "body text"

    def test_frontmatter_and_title(self):
        md = "---\npage_id: \"123\"\n---\n\n# My Title\n\nbody text"
        title, body = strip_frontmatter_and_title(md)
        assert title == "My Title"
        assert body == "body text"

    def test_neither(self):
        md = "just plain content"
        title, body = strip_frontmatter_and_title(md)
        assert title is None
        assert body == "just plain content"

    def test_frontmatter_multiline(self):
        md = "---\npage_id: \"123\"\nspace: DEV\nversion: 5\n---\n\nbody"
        title, body = strip_frontmatter_and_title(md)
        assert title is None
        assert body == "body"
