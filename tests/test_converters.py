import os

from atlassian_local_cli.converters import (
    extract_passthrough_footer,
    extract_unknown_macros,
    md_to_confluence_html,
    postprocess_export_md,
    preprocess_export_html,
    restore_passthrough_blocks,
    rewrite_local_images,
    serialize_passthrough_footer,
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

    def test_colspan_row(self):
        html = '<tr><th colspan="7">BEFORE THE MIGRATION</th></tr>'
        result = preprocess_export_html(html)
        assert "|| BEFORE THE MIGRATION ||" in result
        assert "colspan" not in result

    def test_date(self):
        html = '<time datetime="2026-03-26" class="date-upcoming">26 Mar 2026</time>'
        assert preprocess_export_html(html) == "{date:2026-03-26}"

    def test_task_list_checked(self):
        html = '<ul class="inline-task-list" data-inline-tasks-content-id="123"><li class="checked" data-inline-task-id="1"><span>Done task</span></li></ul>'
        result = preprocess_export_html(html)
        assert "TASK-CHECKED: Done task" in result

    def test_task_list_unchecked(self):
        html = '<ul class="inline-task-list" data-inline-tasks-content-id="123"><li data-inline-task-id="2"><span>Open task</span></li></ul>'
        result = preprocess_export_html(html)
        assert "TASK-UNCHECKED: Open task" in result

    def test_task_list_mixed(self):
        html = '<ul class="inline-task-list" data-inline-tasks-content-id="123"><li class="checked" data-inline-task-id="1"><span>Done</span></li><li data-inline-task-id="2"><span>Open</span></li></ul>'
        result = preprocess_export_html(html)
        assert "TASK-CHECKED: Done" in result
        assert "TASK-UNCHECKED: Open" in result

    def test_info_panel(self):
        html = '<div class="confluence-information-macro confluence-information-macro-information"><p class="title conf-macro-render">My Title</p><span class="aui-icon"></span><div class="confluence-information-macro-body"><p>Body text</p></div></div>'
        result = preprocess_export_html(html)
        assert "PANEL-START: {panel:info|My Title}" in result
        assert "PANEL-BODY: Body text" in result

    def test_warning_panel(self):
        html = '<div class="confluence-information-macro confluence-information-macro-warning"><div class="confluence-information-macro-body"><p>Warning!</p></div></div>'
        result = preprocess_export_html(html)
        assert "PANEL-START: {panel:warning}" in result
        assert "PANEL-BODY: Warning!" in result

    def test_note_panel(self):
        html = '<div class="confluence-information-macro confluence-information-macro-note"><div class="confluence-information-macro-body"><p>Note</p></div></div>'
        result = preprocess_export_html(html)
        assert "{panel:note}" in result

    def test_tip_panel(self):
        html = '<div class="confluence-information-macro confluence-information-macro-tip"><div class="confluence-information-macro-body"><p>Tip</p></div></div>'
        result = preprocess_export_html(html)
        assert "{panel:tip}" in result

    def test_jira_issue_embed(self):
        html = '<span class="jira-issue" data-jira-key="PROJ-123"><a href="https://jira.example.com/browse/PROJ-123" class="jira-issue-key"><img class="icon" src="$iconUrl"/>PROJ-123</a> - <span class="summary">Test issue</span></span>'
        result = preprocess_export_html(html)
        assert result == "{jira:PROJ-123}"

    def test_generic_panel(self):
        html = '<div class="panel" style="border-width: 1px;"><div class="panelHeader" style="border-bottom-width: 1px;"><b>My Title</b></div><div class="panelContent"><p>Body text</p></div></div>'
        result = preprocess_export_html(html)
        assert "PANEL-START: {panel:panel|My Title}" in result
        assert "PANEL-BODY: Body text" in result

    def test_generic_panel_no_header(self):
        html = '<div class="panel" style="border-width: 1px;"><div class="panelContent"><p>Just content</p></div></div>'
        result = preprocess_export_html(html)
        assert "{panel:panel}" in result
        assert "Just content" in result

    def test_expand_section(self):
        html = '<div class="expand-container"><div class="expand-control"><button><span class="expand-control-text conf-macro-render">Click to expand</span></button></div><div class="expand-content" role="region"><p>Hidden content</p></div></div>'
        result = preprocess_export_html(html)
        assert "EXPAND-START: Click to expand" in result
        assert "EXPAND-BODY: Hidden content" in result

    def test_toc_macro_becomes_marker(self):
        html = '<div class="toc-macro rbtoc1234567890"><ul class="toc-indentation"><li><a href="#h1">Heading</a></li></ul></div>'
        result = preprocess_export_html(html)
        assert "[TOC]" in result
        assert "toc-macro" not in result
        assert "Heading" not in result

    def test_task_list_in_table_cell(self):
        html = '<td class="confluenceTd"><ul class="inline-task-list" data-inline-tasks-content-id="123"><li class="checked" data-inline-task-id="1"><span>Done</span></li><li data-inline-task-id="2"><span>Open</span></li></ul></td>'
        result = preprocess_export_html(html)
        assert "[x] Done" in result
        assert "[ ] Open" in result
        # Should be inline, not markdown checkboxes
        assert "- [" not in result
        assert "TASK-" not in result


class TestPostprocessExportMd:
    def test_checked_task(self):
        assert postprocess_export_md("TASK-CHECKED: Done task") == "- [x] Done task"

    def test_unchecked_task(self):
        assert postprocess_export_md("TASK-UNCHECKED: Open task") == "- [ ] Open task"

    def test_mixed_tasks(self):
        md = "TASK-CHECKED: Done\nTASK-UNCHECKED: Open"
        result = postprocess_export_md(md)
        assert "- [x] Done" in result
        assert "- [ ] Open" in result

    def test_no_tasks(self):
        md = "plain text"
        assert postprocess_export_md(md) == "plain text"

    def test_panel_placeholder(self):
        md = "PANEL-START: {panel:info|Title}\nPANEL-BODY: Body text\nPANEL-END"
        result = postprocess_export_md(md)
        assert "> {panel:info|Title}" in result
        assert "> Body text" in result

    def test_panel_no_title(self):
        md = "PANEL-START: {panel:warning}\nPANEL-BODY: Warning!\nPANEL-END"
        result = postprocess_export_md(md)
        assert "> {panel:warning}" in result
        assert "> Warning!" in result

    def test_expand_placeholder(self):
        md = "EXPAND-START: My Title\nEXPAND-BODY: Hidden stuff\nEXPAND-END"
        result = postprocess_export_md(md)
        assert "<details>" in result
        assert "<summary>My Title</summary>" in result
        assert "Hidden stuff" in result
        assert "</details>" in result


class TestPassthrough:
    UNKNOWN_MACRO = '<ac:structured-macro ac:name="cheese"><ac:parameter ac:name="title">Details</ac:parameter><ac:rich-text-body><p>Hidden content</p></ac:rich-text-body></ac:structured-macro>'
    NESTED_MACRO = '<ac:structured-macro ac:name="details"><ac:rich-text-body><ac:structured-macro ac:name="status"><ac:parameter ac:name="title">OK</ac:parameter></ac:structured-macro></ac:rich-text-body></ac:structured-macro>'

    def test_extract_unknown_macros(self):
        storage = f'<p>Before</p>{self.UNKNOWN_MACRO}<p>After</p>'
        _, mapping = extract_unknown_macros("<p>rendered</p>", storage)
        assert len(mapping) == 1
        assert self.UNKNOWN_MACRO in list(mapping.values())[0]

    def test_extract_skips_known_macros(self):
        storage = '<ac:structured-macro ac:name="status"><ac:parameter ac:name="title">OK</ac:parameter></ac:structured-macro>'
        _, mapping = extract_unknown_macros("", storage)
        assert len(mapping) == 0

    def test_extract_nested_macros(self):
        storage = self.NESTED_MACRO
        _, mapping = extract_unknown_macros("", storage)
        assert len(mapping) == 1
        xml = list(mapping.values())[0]
        assert xml.count("<ac:structured-macro") == 2
        assert xml.count("</ac:structured-macro>") == 2

    def test_serialize_footer(self):
        mapping = {"CONFLUENCE-PASSTHROUGH-0": "<macro/>"}
        footer = serialize_passthrough_footer(mapping)
        assert "confluence-passthrough-start" in footer
        assert "confluence-passthrough-stop" in footer
        assert "CONFLUENCE-PASSTHROUGH-0:" in footer
        assert "<macro/>" in footer

    def test_serialize_empty(self):
        assert serialize_passthrough_footer({}) == ""

    def test_extract_footer(self):
        md = "body text\n<!-- confluence-passthrough-start -->\n<!-- confluence-passthrough\nCONFLUENCE-PASSTHROUGH-0:\n<macro/>\n:CONFLUENCE-PASSTHROUGH-0 -->\n<!-- confluence-passthrough-stop -->\n"
        cleaned, mapping = extract_passthrough_footer(md)
        assert "body text" in cleaned
        assert "confluence-passthrough" not in cleaned
        assert mapping["CONFLUENCE-PASSTHROUGH-0"] == "<macro/>"

    def test_extract_footer_missing(self):
        md = "just body text"
        cleaned, mapping = extract_passthrough_footer(md)
        assert cleaned == md
        assert mapping == {}

    def test_restore_with_marker(self):
        html = "<p>CONFLUENCE-PASSTHROUGH-0</p>"
        result = restore_passthrough_blocks(html, {"CONFLUENCE-PASSTHROUGH-0": "<macro/>"})
        assert result == "<macro/>"

    def test_restore_without_marker_appends(self):
        html = "<p>Regular content</p>"
        result = restore_passthrough_blocks(html, {"CONFLUENCE-PASSTHROUGH-0": "<macro/>"})
        assert "<p>Regular content</p>" in result
        assert "<macro/>" in result

    def test_restore_inline_marker(self):
        html = "<td>CONFLUENCE-PASSTHROUGH-0</td>"
        result = restore_passthrough_blocks(html, {"CONFLUENCE-PASSTHROUGH-0": "<macro/>"})
        assert result == "<td><macro/></td>"

    def test_restore_deleted_marker(self):
        html = "<p>Content only</p>"
        mapping = {"CONFLUENCE-PASSTHROUGH-0": "<macro1/>", "CONFLUENCE-PASSTHROUGH-1": "<macro2/>"}
        result = restore_passthrough_blocks(html, mapping)
        assert "<macro1/>" in result
        assert "<macro2/>" in result

    def test_round_trip(self):
        mapping = {"CONFLUENCE-PASSTHROUGH-0": self.UNKNOWN_MACRO}
        footer = serialize_passthrough_footer(mapping)
        md = f"Some content\n\nCONFLUENCE-PASSTHROUGH-0\n{footer}"
        result = md_to_confluence_html(md)
        assert 'ac:name="cheese"' in result
        assert "Hidden content" in result


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

    def test_code_block_escapes_cdata_terminator(self):
        """Code containing ']]>' must not prematurely terminate the wrapping CDATA."""
        md = "```xml\n<![CDATA[payload]]>\n```"
        result = md_to_confluence_html(md)
        # The raw sequence ']]>' must not appear inside the plain-text-body except
        # as the deliberate split+reopen that re-escapes it.
        body_start = result.find("<ac:plain-text-body>") + len("<ac:plain-text-body>")
        body_end = result.find("</ac:plain-text-body>")
        body = result[body_start:body_end]
        # The escaped form: ']]]]><![CDATA[>' appears exactly where the original had ']]>'
        assert "]]]]><![CDATA[>" in body
        # Still semantically represents the original payload
        assert "payload" in body

    def test_footnotes_supported(self):
        md = "Here is a footnote ref[^1].\n\n[^1]: Footnote text."
        result = md_to_confluence_html(md)
        # markdown 'footnotes' extension emits a <sup> reference and a <div class="footnote">
        assert 'class="footnote"' in result
        assert "Footnote text" in result

    def test_toc_marker_becomes_macro(self):
        result = md_to_confluence_html("[TOC]")
        assert 'ac:name="toc"' in result
        assert "[TOC]" not in result

    def test_iframe_wrapped_in_html_macro(self):
        md = '<iframe src="https://example.com/embed" width="600"></iframe>'
        result = md_to_confluence_html(md)
        assert 'ac:name="html"' in result
        assert "CDATA[<iframe" in result
        assert 'src="https://example.com/embed"' in result

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

    def test_date_conversion(self):
        result = md_to_confluence_html("Due: {date:2026-04-15}")
        assert '<time datetime="2026-04-15" />' in result

    def test_task_list_checked(self):
        md = "- [x] Done task\n- [ ] Open task"
        result = md_to_confluence_html(md)
        assert "<ac:task-list>" in result
        assert "<ac:task-status>complete</ac:task-status>" in result
        assert "<ac:task-status>incomplete</ac:task-status>" in result
        assert "Done task" in result
        assert "Open task" in result

    def test_task_list_uppercase_x(self):
        md = "- [X] Done task"
        result = md_to_confluence_html(md)
        assert "<ac:task-status>complete</ac:task-status>" in result

    def test_panel_info_with_title(self):
        md = "> {panel:info|My Title}\n> Panel content here"
        result = md_to_confluence_html(md)
        assert 'ac:name="info"' in result
        assert 'ac:name="title">My Title<' in result
        assert "Panel content here" in result

    def test_panel_warning_no_title(self):
        md = "> {panel:warning}\n> Danger zone"
        result = md_to_confluence_html(md)
        assert 'ac:name="warning"' in result
        assert "ac:name=\"title\"" not in result
        assert "Danger zone" in result

    def test_expand_to_confluence(self):
        md = "<details>\n<summary>Click me</summary>\n\nHidden content here\n\n</details>"
        result = md_to_confluence_html(md)
        assert 'ac:name="expand"' in result
        assert 'ac:name="title">Click me<' in result
        assert "Hidden content here" in result
        assert "<details>" not in result

    def test_expand_not_wrapped_in_p(self):
        md = "Before\n\n<details>\n<summary>Title</summary>\n\nBody\n\n</details>\n\nAfter"
        result = md_to_confluence_html(md)
        assert "<p><ac:structured-macro" not in result

    def test_panel_not_wrapped_in_p_tag(self):
        md = "> {panel:info|Title}\n> Content here"
        result = md_to_confluence_html(md)
        assert "<p><ac:structured-macro" not in result
        assert 'ac:name="info"' in result

    def test_panel_multi_paragraph(self):
        md = "> {panel:info|Title}\n> First para.\n>\n> Second para."
        result = md_to_confluence_html(md)
        assert "First para." in result
        assert "Second para." in result
        assert result.count("<ac:rich-text-body>") == 1

    def test_panel_all_types(self):
        for ptype in ("info", "note", "warning", "tip", "panel"):
            md = f"> {{panel:{ptype}}}\n> Content"
            result = md_to_confluence_html(md)
            assert f'ac:name="{ptype}"' in result

    def test_jira_issue_embed(self):
        result = md_to_confluence_html("See {jira:PROJ-123} for details.")
        assert 'ac:name="jira"' in result
        assert 'ac:name="key">PROJ-123<' in result

    def test_jira_issue_in_table(self):
        md = "| Issue | Status |\n|---|---|\n| {jira:PROJ-456} | {status:DONE|green} |"
        result = md_to_confluence_html(md)
        assert 'ac:name="jira"' in result
        assert 'ac:name="status"' in result

    def test_colspan_row_in_table(self):
        md = "| A | B |\n|---|---|\n|| SECTION HEADER ||\n| 1 | 2 |"
        result = md_to_confluence_html(md)
        assert 'colspan="2"' in result
        assert "SECTION HEADER" in result

    def test_colspan_multiple_sections(self):
        md = "| A | B | C |\n|---|---|---|\n|| FIRST ||\n| 1 | 2 | 3 |\n|| SECOND ||\n| 4 | 5 | 6 |"
        result = md_to_confluence_html(md)
        assert result.count('colspan="3"') == 2
        assert "FIRST" in result
        assert "SECOND" in result

    def test_colspan_with_leading_empty_cells(self):
        """Colspan marker may end up in a non-first cell when table lacks leading pipe."""
        md = "| A | B | C |\n|---|---|---|\n|| HEADER ||\n| 1 | 2 | 3 |"
        result = md_to_confluence_html(md)
        assert 'colspan="3"' in result
        assert "HEADER" in result
        # Should NOT have empty td cells in the colspan row
        assert "<td></td>" not in result.split("HEADER")[0].split("</thead>")[-1]


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


class TestRewriteLocalImages:
    def test_local_image_rewritten(self, tmp_path):
        img = tmp_path / "screenshot.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")
        html = '<p><img alt="Screenshot" src="screenshot.png" /></p>'
        result, images = rewrite_local_images(html, str(tmp_path))
        assert '<ac:image ac:alt="Screenshot">' in result
        assert 'ri:filename="screenshot.png"' in result
        assert "<img" not in result
        assert images == [("screenshot.png", str(img))]

    def test_local_image_in_subdir(self, tmp_path):
        subdir = tmp_path / "images"
        subdir.mkdir()
        img = subdir / "diagram.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")
        html = '<img src="images/diagram.png" />'
        result, images = rewrite_local_images(html, str(tmp_path))
        assert 'ri:filename="diagram.png"' in result
        # Path stored for upload must be absolute, not the relative src
        assert images[0][0] == "diagram.png"
        assert os.path.isabs(images[0][1])

    def test_http_image_left_untouched(self, tmp_path):
        html = '<img alt="logo" src="https://example.com/logo.png" />'
        result, images = rewrite_local_images(html, str(tmp_path))
        assert result == html
        assert images == []

    def test_missing_local_file_left_untouched(self, tmp_path):
        html = '<img src="not-there.png" />'
        result, images = rewrite_local_images(html, str(tmp_path))
        assert result == html
        assert images == []

    def test_deduplicates_repeated_image(self, tmp_path):
        img = tmp_path / "foo.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")
        html = '<img src="foo.png" /><p>mid</p><img src="foo.png" />'
        _, images = rewrite_local_images(html, str(tmp_path))
        assert len(images) == 1

    def test_no_alt_attribute(self, tmp_path):
        img = tmp_path / "plain.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")
        html = '<img src="plain.png" />'
        result, _ = rewrite_local_images(html, str(tmp_path))
        # No ac:alt attribute when alt is missing or empty
        assert "<ac:image>" in result
        assert "ac:alt" not in result

    def test_absolute_path_left_untouched(self, tmp_path):
        html = '<img src="/etc/passwd" />'
        result, images = rewrite_local_images(html, str(tmp_path))
        assert result == html
        assert images == []

    def test_data_uri_left_untouched(self, tmp_path):
        html = '<img src="data:image/png;base64,AAA" />'
        result, images = rewrite_local_images(html, str(tmp_path))
        assert result == html
        assert images == []
