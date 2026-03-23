from atlassian_local_cli.converters import (
    md_to_confluence_html,
    postprocess_export_md,
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
