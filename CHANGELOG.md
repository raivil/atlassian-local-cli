# Changelog

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
