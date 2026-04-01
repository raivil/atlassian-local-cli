# Changelog

## v1.3.0 (2026-04-01)

### Added
- Expand/collapse section support: `<details><summary>Title</summary>` syntax converts to/from Confluence `expand` macro
- 123 tests with 100% coverage

## v1.2.0 (2026-03-31)

### Added
- Epic support: `jira-create --type Epic` auto-sets the Epic Name field
- `--epic PROJ-100` flag on `jira-create` to link new issues to an Epic
- `jira-link-epic` command to assign existing issues to an Epic (supports multiple issues)
- Auto-detection of Epic custom field IDs from Jira API, with env var overrides (`JIRA_EPIC_NAME_FIELD`, `JIRA_EPIC_LINK_FIELD`)
- 119 tests with 100% coverage

## v1.1.0 (2026-03-31)

### Added
- `jira-create` command to create Jira issues from the CLI
- Multiline description support via `--description-file` (reads from file or stdin with `-`)
- `--description` and `--description-file` are mutually exclusive
- Optional `--priority` and `--assignee` flags
- `make jira-create` target
- 110 tests with 100% coverage

## v1.0.1 (2026-03-23)

### Fixed
- Panel blocks no longer produce invalid XHTML — conversion now happens after markdown parsing to avoid `<p>` wrapping `<ac:structured-macro>` elements
- Multi-paragraph panels now work correctly (blank `>` lines are preserved)

## v1.0.0 (2026-03-23)

### Added
- Passthrough preservation for unknown Confluence macros (details, expand, anchor, toc, etc.)
- Unknown macros are extracted from storage XML and stored as HTML comments in the markdown footer
- On import, passthrough blocks are restored as raw XML into Confluence storage format
- Stack-based XML parser handles nested macros correctly
- `beautifulsoup4` added as explicit dependency
- 103 tests with 100% coverage

## v0.9.0 (2026-03-23)

### Added
- Jira issue embed support: `{jira:PROJ-123}` syntax converts to/from Confluence Jira issue macro
- Generic panel support: `> {panel:panel|Title}` for Confluence styled panels

### Fixed
- Task lists inside table cells no longer break XHTML upload; rendered as compact inline format `[x] Done; [ ] Open`

## v0.8.0 (2026-03-23)

### Added
- Jira issue embed support: `{jira:PROJ-123}` syntax converts to/from Confluence Jira issue macro
- Generic panel support: `> {panel:panel|Title}` for Confluence styled panels (in addition to info/note/warning/tip)
- 90 tests with 100% coverage

## v0.7.0 (2026-03-23)

### Added
- Info/note/warning/tip panel support: `> {panel:info|Title}` blockquote syntax converts to/from Confluence `ac:structured-macro` panels
- All 4 panel types: `info`, `note`, `warning`, `tip`
- 85 tests with 100% coverage

## v0.6.0 (2026-03-23)

### Added
- Task list support: `- [x]` / `- [ ]` markdown checkboxes convert to/from Confluence `ac:task-list`
- Date support: `{date:YYYY-MM-DD}` syntax converts to/from Confluence `<time>` elements
- 76 tests with 100% coverage

## v0.5.1 (2026-03-20)

### Fixed
- Colspan row regex now handles empty cells before the marker when tables lack a leading pipe delimiter

## v0.5.0 (2026-03-20)

### Added
- Colspan support for table section headers: `|| SECTION HEADER ||` syntax spans all columns automatically
- Column count auto-detected from the table's header row

### Fixed
- Section headers like "BEFORE THE MIGRATION" no longer produce empty cells when uploaded to Confluence

## v0.4.0 (2026-03-20)

### Added
- Status badges support: `{status:DONE|green}` syntax in markdown, converts to/from Confluence `ac:structured-macro` status lozenges (green, red, blue, yellow, grey)
- User mentions support: `@username` syntax in markdown, converts to/from Confluence `ac:link` user references
- Full test suite with pytest (61 tests, 100% coverage)
- `make test` and `make test-cov` targets

### Changed
- Refactored from single-file `main.py` into `src/atlassian_local_cli/` package with modules: `config`, `clients`, `converters`, `wiki`, `jira_commands`, `cli`
- `Config` is now a frozen dataclass with lazy loading/caching (testable without side effects)
- Switched build system from setuptools to hatchling (src layout)
- `main.py` is now a backward-compat shim for PyInstaller

## v0.3.0 (2026-03-20)

### Added
- YAML frontmatter on wiki export with page metadata (page_id, space, version, author, created/updated dates, url)
- `jira-my-tasks` filters: `--status` (open/closed/all), `--status-name`, `--type`, `--project`
- `jira-my-tasks` command with `--json` output for integrations and table format for terminal
- `jira-transition` command to move issues between statuses
- `make build` and `make clean` targets for standalone binary builds via PyInstaller
- GitHub Actions CI for automated binary builds (macOS arm64, macOS x86_64, Linux x86_64)

### Changed
- Switched from raw `requests` to `atlassian-python-api` for Confluence and Jira API calls
- `--status open` now filters by `statusCategory != "Done"` instead of `resolution = Unresolved`
- Jira auth always uses Bearer token (PATs don't work with basic auth)

### Fixed
- Code blocks now render correctly in Confluence using `ac:structured-macro` instead of plain `<pre><code>`
- Frontmatter and title heading are properly stripped before uploading to avoid duplicates

## v0.2.0 (2026-03-20)

### Added
- `wiki-export` command to export Confluence pages to Markdown
- `wiki-update` command to update a Confluence page from a Markdown file
- `wiki-create` command to create new Confluence pages
- `jira-get` command to display Jira issue details
- Configuration via `~/.config/atlassian-local-cli/.env`

## v0.1.0 (2026-03-20)

- Initial prototype with basic Confluence page export
