# Changelog

## v2.2.0 (2026-06-01)

### Fixed
- `jira-transition` no longer crashes on every transition against this Jira instance. The command resolved the transition itself, then called the library's `issue_transition()` (an alias for `set_issue_status()`), which re-interprets its argument as a *status name* and re-resolves it via `get_transition_id_to_status_name()` — that calls `.lower()` on the value and raised `AttributeError: 'int' object has no attribute 'lower'`, because `get_issue_transitions()` returns transition ids as ints. It now posts the already-resolved id directly via `set_issue_status_by_transition_id`.
- Transition-by-id (e.g. `jira-transition KEY 41`) now matches against the real instance. Matching compared `t["id"] == args.status` (int vs str, always false since the library returns int ids); it now compares as strings.

### Added
- `jira-transition --resolution "Won't Do"` sets a resolution as part of the transition (e.g. to close an issue as Won't Do). The name is validated case-insensitively against `get_all_resolutions()` — a typo gives a clear error listing the valid resolutions — and is posted as a `fields.resolution` payload. Only works on transitions whose workflow screen includes the resolution field; otherwise Jira rejects it with a 400. New `RESOLUTION=` passthrough on the `jira-transition` Make target.

## v2.1.1 (2026-06-01)

### Fixed
- `@mention` conversion on upload (`md_to_confluence_html`) no longer fires inside code. Inline code spans and fenced code blocks are now left verbatim, so references like `` `@modelcontextprotocol/sdk` `` (an npm scope) or `` `@kind path-problem` `` (CodeQL metadata) no longer get rewritten into `<ac:link><ri:user .../></ac:link>`, which Confluence rendered as literal escaped markup on the page. Scoped-package refs (`@scope/pkg`) outside code are also no longer treated as mentions. Genuine prose mentions (`@jdoe`) are unaffected. Adds 3 regression tests.

## v2.1.0 (2026-05-21)

### Added
- Multi-account context support (kubectl-style). Config resolves from `--context <name>` → `current-context` file → `default` (`.env`), with named contexts stored under `contexts/<name>.env`. New `context` subcommands: `list`, `current`, `use <name>`, `unset`, `show [name]`. Every Make target accepts `CONTEXT=<name>`. Shell env vars still override file values.

## v2.0.0 (2026-05-13)

### Added
- `jira-update` — patch individual attributes on an existing issue: `--summary`, `--description`/`--description-file`, `--priority`, `--assignee` (use `none` to unassign), `--type`, `--epic` (`none` to unlink), `--label` (replace), `--add-label`/`--remove-label` (mutate), and `--field key=value` for arbitrary custom fields (value parsed as JSON when possible).
- New commands inspired by [ankitpokhrel/jira-cli](https://github.com/ankitpokhrel/jira-cli):
  - `jira-me` — print the current Jira user.
  - `jira-open` — open the issue in a browser (or `--print-url` only).
  - `jira-search` — rich JQL search with raw `--jql` and/or builder flags (`--assignee me|none`, `--reporter`, `--priority`, `--label`, `--status`/`--status-name`, `--type`, `--project`), plus `--order-by`/`--reverse`/`--limit` and `--json`/`--csv` output.
  - `jira-comment` / `jira-comments` — add a comment (inline, file, or stdin) and list comments on an issue.
  - `jira-link` / `jira-unlink` / `jira-link-types` — generic issue links (`Blocks`, `Relates`, `Duplicates`, ...).
  - `jira-worklog` — log work with Jira-style time syntax (`"1w 2d 3h 30m"`; `1w=5d, 1d=8h`; bare integer = minutes).
  - `jira-sprints` / `jira-sprint-add` / `jira-sprint-issues` — list board sprints, add issues to a sprint, list issues in a sprint.
  - `jira-clone` — clone an issue with optional `--summary` override and repeatable `--replace find:replace` on summary/description.
  - `jira-delete` — delete an issue; requires `--yes`, optional `--cascade` for sub-tasks.
  - `jira-epics` / `jira-epic-issues` — list epics (filterable by project/status) and list a given epic's children (Agile API with JQL fallback on the Epic Link field).
- Make targets for every new command.
- 194 tests with 100% coverage.

### Fixed
- `jira-link-epic` no longer double-wraps the request body in `{"fields": ...}` — `atlassian-python-api`'s `issue_update` already wraps for you, so the prior call was sending a malformed payload.

### Changed
- Dependency bumps: `requests` 2.34.1, `urllib3` 2.7.0, `pytest` 9.0.3, `pytest-cov` 7.1.0, `coverage` 7.14.0, `idna` 3.15, `packaging` 26.2, `certifi` 2026.4.22, `pyinstaller` 6.20.0, `pygments` 2.20.0.

## v1.4.0 (2026-04-09)

### Added
- Local image upload: `![alt](./pic.png)` in markdown uploads the file as a page attachment and rewrites to `<ac:image><ri:attachment ri:filename="pic.png"/></ac:image>`. External URLs (`http://`, `https://`, `data:`) are left untouched. Paths resolve relative to the input markdown file.
- `[TOC]` marker converts to/from the Confluence `toc` macro on upload and export.
- `<iframe>...</iframe>` tags in markdown are wrapped in the Confluence `html` macro on upload.
- Markdown footnotes (`[^1]`) now render via the `footnotes` extension on upload.
- 137 tests with 100% coverage

### Fixed
- Code blocks containing `]]>` no longer produce invalid storage XML — the sequence is now escaped by splitting and reopening the CDATA section.

## v1.3.1 (2026-04-01)

### Fixed
- Expand sections no longer get captured inside adjacent panels — expand preprocessing now runs before panel preprocessing

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
