# Changelog

## v2.9.0 (2026-09-04)

### Added
- `wiki-attachments <page_id>` — list a Confluence page's attachments (name, size, media type, version, date), or download them with `-o <dir>`. Attachments could only ever move *up* before this: `wiki-update`/`wiki-create` upload local images referenced from the markdown, but nothing could read a page's existing files back, so pulling an incident page's 16 query dumps meant clicking through the browser one at a time. `--match <glob>` filters by filename for both listing and download, `--json` emits the listing for scripting.
  - Pages through `get_attachments_from_content` 50 at a time rather than calling the library's `download_attachments_from_page`, which never pages past the first response and so silently drops attachment 51 onward. Going direct also gets listing, glob filtering and filename handling out of the same code path.
  - Attachment titles are server-supplied and land in an `open()` path, so each one is basenamed and stripped of `<>:"/\|?*` and control characters before use; titles colliding after sanitization get a ` (1)` suffix instead of overwriting each other, and any destination whose resolved path leaves the target directory (a pre-existing symlink, say) is skipped with a warning rather than followed.
  - Existing files are overwritten with no `--force` gate: an attachment can be updated in place on the page, and a skip-by-default would make the common case — re-pull the current version — silently do nothing.

## v2.8.0 (2026-09-01)

### Added
- `context add <name>` — create a context without hand-writing `contexts/<name>.env`. Previously `context list|current|use|unset|show` could all read contexts but nothing could create one, so adding a second account meant knowing the file layout and the exact env-var names. Prompts for any value not passed as a flag, reading tokens through `getpass` so they never reach shell history or `ps`; prompting is TTY-gated, so scripted use (`--jira-url ... --jira-token ...`) works and omitted values fall back to defaults instead of blocking. Writes `0600` files into a `0700` `contexts/` dir, refuses to clobber an existing context without `--force`, and validates the name against `^[A-Za-z0-9][A-Za-z0-9._-]*$` so it can't escape `CONTEXTS_DIR` via `../`. Does not switch the active context — it prints the `context use` next step instead. `make context-add NAME=<name>` target added.
- Atlassian **Cloud** support for Jira. `create_jira()` previously always sent `Authorization: Bearer <token>`, which Cloud rejects with a 401 — Cloud wants the account email plus an API token over basic auth. Auth mode is now chosen by URL: hosts under `*.atlassian.net` use basic auth with the new `JIRA_USERNAME` key, everything else keeps the Bearer/PAT path for Server/Data Center. `JIRA_AUTH=basic|bearer` overrides the detection, for Cloud on a custom domain. A Cloud context that omits `JIRA_USERNAME` now fails with a message naming the missing key instead of a bare `HTTPError` traceback.
  - Detection is keyed on the URL rather than on `JIRA_USERNAME` being present: `JIRA_USERNAME` was read by nothing before this release, so existing Server/DC context files carry stray username lines. Switching on the username flipped those working PAT configs to basic auth and 401'd them — caught in testing against a real Server instance.
- `jira-me` prints `displayName <emailAddress>` when the instance provides them. Cloud's `myself()` returns no `name` field, so the old `name → accountId → key` fallback printed an opaque account UUID.

### Fixed
- `context add` warns when a key it just wrote is also exported in the shell. Shell env wins over file values in `load_config()`, so a `JIRA_TOKEN` in your profile silently defeats every context you create — it surfaced only as a confusing auth failure much later.

## v2.7.0 (2026-08-14)

### Added
- `wiki-delete <page_id> --yes [--cascade]` — delete a Confluence page (moves it to trash; `--cascade` also deletes child pages). Previously there was no way to remove a page short of dropping to the underlying `atlassian-python-api` library directly — only `jira-delete` existed for Jira issues. Mirrors `jira-delete`'s `--yes`-required confirmation pattern. `make wiki-delete PAGE=<id> YES=1` target added alongside it.

## v2.6.0 (2026-08-14)

### Fixed
- `wiki-update` no longer corrupts (or outright fails to upload) a page containing a tag-like placeholder in prose, e.g. literal text `<table>` used as an example ("add `<table>` to BigQuery") outside a code span. Python-Markdown's raw-HTML passthrough treated it as a genuine unclosed tag, so everything parsed after it was nested inside that element — Confluence then rejected the upload with `Error parsing xhtml: Unexpected close tag ...; expected </table>`, and even a byte-for-byte unmodified re-upload of an affected page failed the same way. Added `_escape_unmatched_tags()`: a lightweight per-tag-name stack match over the HTML already produced by `md_lib.markdown()` (including the nested calls that render panel/expand/page-property bodies), escaping only tokens with no matching open/close partner anywhere in the document. Runs after markdown parsing rather than on the raw source, so real code (fenced/inline/indented) — already HTML-escaped by the parser itself — and genuine autolinks need no special-casing, and well-formed raw HTML this module relies on elsewhere (`<iframe>`, `<br>`, `ac:*`/`ri:*` macro XML) is left untouched regardless of tag name, since a matched pair is never flagged. 5 regression tests.
- `@@TOKEN@@`-style double-`@` template placeholders (e.g. dbt's `@@DEST_DATASET@@`, meant to be swapped per-environment and left otherwise untouched) were silently rewritten into a Confluence user-link for a nonexistent user. The `@mention` regex's negative lookbehind excluded a preceding quote or word character but not `@` itself, so the second `@` of the pair read as a bare mention (`@DEST_DATASET`). This one doesn't fail loudly — it was only caught by inspecting a real page after fixing the bug above, since every prior upload of that page had crashed before reaching this code path. Added `@` to the lookbehind exclusion. 1 regression test.

## v2.5.0 (2026-08-12)

### Added
- `--version` / `-v` — prints the installed version (e.g. `atlassian-local-cli 2.4.1`); previously there was no way to check which build was installed. Reads the version from installed package metadata (`importlib.metadata`) rather than a hardcoded string, so it can't drift from `pyproject.toml`.

### Fixed
- Removed two stale, gitignored `.egg-info` directories left over at the repo root from a pre-rename build (`wiki_to_md.egg-info`, and an `atlassian_local_cli.egg-info` pinned at `0.3.0`). Because `importlib.metadata` scans `sys.path` — which includes the current directory — running `uv run atlassian-local-cli` from the repo root resolved the wrong, ancient version instead of the one actually installed in the venv. This is also why `--version` is only being added now: there was no reliable metadata to read until this was cleaned up.
- PyInstaller builds (`make build` and the release CI in `.github/workflows/build.yml`) now pass `--copy-metadata atlassian-local-cli`. Without it, the frozen binary has no package metadata at all, so `importlib.metadata.version(...)` would raise `PackageNotFoundError` — crashing not just `--version` but every command, since the version is resolved once at parser construction. CI's binary smoke-test now also runs `--version` to catch this class of regression.

## v2.4.1 (2026-08-12)

### Fixed
- `wiki-export` no longer word-wraps long table-cell text across multiple physical lines. The page-body `html2text.HTML2Text()` instance in `wiki.py` never set `body_width`, so it kept the library default (78 cols); html2text's own "don't wrap table rows" heuristic looks for a space *before* the pipe, but its generated rows are `cell1| cell2` (no leading space), so it never actually exempted its own table syntax from wrapping. A long cell would spread across several lines, with only the true row end carrying html2text's row-terminating two-space marker — indistinguishable from a `<br>`-induced mid-cell break in one direction, and from a table-final row (which loses that marker at end-of-document) in the other. Set `h.body_width = 0`, matching the precedent already used for Page Properties cells in `converters.py`. Adds a regression test asserting a long cell's full text stays on the row's single line.

## v2.4.0 (2026-07-28)

### Fixed
- `wiki-export` no longer **hangs forever** on pages containing a self-closing macro (`<ac:structured-macro ... />` — e.g. the `children` / page-tree macro used on index pages). `_find_top_level_macros` scanned for a closing tag that such an element never has; on failing to find one it broke out of the inner scan **without advancing the outer cursor**, so the next iteration re-found the same offset and looped indefinitely. It hung both when the self-closing macro was top-level and when it was nested inside a paired macro (an unbalanced depth counter left the outer element unterminated). Rewritten as a single forward pass over open/close/self-closing tokens, which cannot loop by construction and no longer mis-pairs a self-closing macro with a later element's closing tag. Adds 6 regression tests, each guarded by an alarm so a regression fails loudly instead of wedging the suite.

### Added
- `wiki-raw <page_id>` — dump a page's unconverted HTML, for diagnosing exports that fail, hang or lose content. `--format storage|export|both` (default `storage`), `--macros` to list the page's top-level macros and flag which are self-closing, `-o` to write to a file. Because it skips the converter entirely, it still works on pages the exporter cannot process.

## v2.3.2 (2026-07-15)

### Fixed
- `wiki-export` → `wiki-update` no longer corrupts (or destroys) a table that has an **empty leading or trailing cell** — e.g. a comparison table with an empty top-left corner and headers across the top. `html2text` renders an empty edge cell as a bare edge pipe, which GFM treats as an optional delimiter: the cell collapses and the row ends up with fewer columns than the `---|---` separator. Python-Markdown then refuses to parse the block as a table at all and re-emits it as a `<p>` full of `<br/>`s, so the table is lost on round-trip. Empty cells are now filled with a sentinel before `html2text` (`_fill_empty_table_cells`, at the end of `preprocess_export_html`) and stripped afterwards, re-emitting each affected row with explicit edge pipes so empty cells survive GFM re-parsing (`_restore_empty_table_cells` in `postprocess_export_md`). Only pages that actually contain an empty cell are touched — all other output is byte-identical. Adds 4 regression tests.

## v2.3.1 (2026-07-06)

### Fixed
- `wiki-export` → `wiki-update` no longer corrupts tables whose cells contain block-level content (headings, lists, multiple paragraphs, non-inline macros). Such cells render across multiple lines through `html2text`, producing GFM-invalid markdown that Python-Markdown then re-parses lossily — leaking cell content out of the table as sibling `<h4>`/`<p>` elements and destroying the table on round-trip. Unsafe tables are now preserved **verbatim** in storage format via the passthrough footer: on export each is matched to its storage-format `<table>` by document order (report/page-property tables are removed first, so the remainder correspond 1:1) and swapped for a passthrough placeholder; if the export-view and storage table counts don't line up, it refuses to substitute and leaves every table unconverted. Simple, inline-only tables continue to convert to editable Markdown unchanged (a lone inline status lozenge stays safe/editable). Adds `extract_unsafe_tables`, `_cell_is_unsafe`, and `_find_top_level_tables` in `converters.py`, wired into `wiki_export`; 8 regression tests.

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
