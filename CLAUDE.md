# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

CLI tool (`atlassian-local-cli`) for interacting with Confluence and Jira. Uses `atlassian-python-api` for API calls, `html2text` for HTML→MD export, and `markdown` for MD→HTML upload.

## Commands

```bash
make setup                                                  # Install dependencies (uv sync)
make test                                                   # Run tests
make test-cov                                               # Run tests with coverage (terminal + HTML)
uv run pytest tests/test_converters.py::TestMdToConfluenceHtml::test_status_badge  # Run a single test
make build                                                  # Build standalone binary (PyInstaller)
make clean                                                  # Remove build artifacts
make wiki-export PAGE=<id> [OUTPUT=out.md]                  # Export Confluence page
make wiki-update PAGE=<id> INPUT=<file.md>                  # Update Confluence page
make wiki-raw PAGE=<id> [MACROS=1]                          # Dump raw page HTML / list macros (debug exports)
make wiki-create SPACE=<key> TITLE="title" INPUT=<file.md>  # Create Confluence page
make wiki-delete PAGE=<id> YES=1 [CASCADE=1]                # Delete Confluence page (moves to trash)
make jira-get ISSUE=<key>                                   # Display a Jira issue
make jira-my-tasks [JSON=1] [LIMIT=50]                      # List your assigned tasks
make jira-transition ISSUE=<key> [STATUS="<status>"] [RESOLUTION="Won't Do"]  # Transition issue (omit STATUS to list options)
make jira-update ISSUE=<key> [SUMMARY=...] [PRIORITY=...]   # Update individual attributes
make jira-me                                                # Print current user
make jira-open ISSUE=<key>                                  # Open issue in browser
make jira-search [JQL=...] [ASSIGNEE=me] [PROJECT=...]      # Search Jira with JQL/filters
make jira-comment ISSUE=<key> BODY="..."                    # Add a comment
make jira-comments ISSUE=<key>                              # List comments
make jira-link FROM=<key> TO=<key> TYPE=Blocks              # Link two issues
make jira-unlink LINK_ID=<id>                               # Remove a link
make jira-link-types                                        # List link types
make jira-worklog ISSUE=<key> TIME="2h 30m"                 # Log work
make jira-sprints BOARD=<id>                                # List sprints on a board
make jira-sprint-add SPRINT=<id> ISSUES="A-1 A-2"           # Add issues to sprint
make jira-sprint-issues SPRINT=<id>                         # List issues in sprint
make jira-clone ISSUE=<key> [REPLACE="old:new"]             # Clone an issue
make jira-delete ISSUE=<key> YES=1 [CASCADE=1]              # Delete an issue
make jira-epics [PROJECT=PROJ]                              # List epics
make jira-epic-issues EPIC=<key>                            # List children of an epic
make context-add NAME=<name>                                # Create a new context (prompts for values)
make context-list                                           # List configured contexts (active marked with *)
make context-current                                        # Print active context name
make context-use NAME=<name>                                # Set persistent default context
make context-show [NAME=<name>]                             # Show resolved config (tokens masked)
make context-unset                                          # Revert persistent default to 'default'
uv tool install . --reinstall                               # Install/update globally as `atlassian-local-cli`
```

Every make target accepts `CONTEXT=<name>` to override the active context for that single invocation (e.g., `make jira-get ISSUE=FOO-1 CONTEXT=work`).

## Configuration

Env vars loaded from `~/.config/atlassian-local-cli/.env` (the "default" context). See `.env.example`.

- `WIKI_URL` — defaults to `https://wiki.example.com/`
- `WIKI_USERNAME` / `WIKI_TOKEN` — Confluence auth (basic auth when username set, Bearer otherwise)
- `JIRA_URL` / `JIRA_TOKEN` — Jira auth
- `JIRA_USERNAME` — account email, required for Atlassian Cloud (basic auth). Ignored on Server/DC.
- `JIRA_AUTH` — `basic` or `bearer`, forcing the auth mode. Only needed for Cloud on a custom domain (which URL detection can't spot) or to opt a `*.atlassian.net` host out of basic auth.

### Contexts (multi-account)

Multiple accounts are supported kubectl-style. Storage layout:

```
~/.config/atlassian-local-cli/
  .env                       # the "default" context
  contexts/
    work.env                 # named context, selected via --context work
    personal.env
  current-context            # plain text; persistent default set via `context use`
```

Resolution order (highest priority first):
1. `--context <name>` flag passed on the command line
2. `current-context` file contents (set via `atlassian-local-cli context use <name>`)
3. `default` (i.e. `.env`)

Shell env vars (e.g. `JIRA_TOKEN=...`) still win over file values, matching prior behavior.

Create a context with `atlassian-local-cli context add <name>`: it prompts for any value not passed as a flag (tokens via `getpass`), writes `0600`, and refuses to overwrite without `--force`. Prompting is TTY-gated so scripted use works. It does not switch the active context.

The `--context` flag must appear **before** the subcommand: `atlassian-local-cli --context work jira-get FOO-1`. Management commands: `context list | current | use <name> | unset | show [name]`.

## Architecture

Python package in `src/atlassian_local_cli/` with `main.py` as a backward-compat shim for PyInstaller. Entry point `atlassian_local_cli.cli:main`. Managed with `uv` and built with `hatchling`.

- **`config.py`** — `Config` dataclass + `get_config()` with lazy loading/caching. `reset_config()` for test isolation. Multi-context: `set_active_context(name)` (from `--context` flag, clears cache), `set_current_context(name)` (persists to `current-context` file), `list_contexts()`, `context_env_path(name)`, `context_exists(name)`, `resolve_context_name()`, `validate_context_name()` (rejects names that would escape `CONTEXTS_DIR`), `write_context_env()` (backs `context add`; `0600` file in a `0700` dir, double-quoted/escaped values), `ContextNotFoundError`, `ContextExistsError`, `InvalidContextNameError`. Uses `dotenv_values` (not `load_dotenv`) so context switches don't pollute `os.environ` across calls within a single process.
- **`clients.py`** — `create_confluence()` / `create_jira()` factory functions. Confluence picks auth by `WIKI_USERNAME` (set → basic, unset → Bearer). Jira picks by **URL**, not username: `_jira_uses_basic_auth()` sends basic auth for `*.atlassian.net` (Cloud wants email + API token and 401s on Bearer) and a Bearer PAT otherwise (Server/DC 401s on basic). `JIRA_AUTH=basic|bearer` overrides the detection. Keying off `JIRA_USERNAME` instead would break the many Server configs carrying a stray, previously-unread username line.
- **`converters.py`** — all pure transformation functions:
  - `preprocess_export_html()` — converts Confluence HTML to markdown tokens before html2text (status badges → `{status:TITLE|colour}`, user mentions → `@username`)
  - `md_to_confluence_html()` — converts markdown to Confluence storage format. Processes status badges and `@username` *before* the markdown parser (to avoid `|` in `{status:X|colour}` breaking table parsing), then transforms `<pre><code>` into `ac:structured-macro` code macros
  - Colspan table section headers: `|| TEXT ||` in markdown ↔ `<th colspan="N">` in Confluence. Column count auto-detected from thead.
  - Page Properties (`details` macro) ↔ `<!-- page-properties[ id=X] -->` directive above a markdown table. The first row is a cosmetic header (discarded on upload); each subsequent row becomes a property (`<th>` key + `<td>` value). Upload builds the macro in `extract_page_properties()`/`_build_details_macro()` (cell values reuse `{status}`/`@user`/`{date}`/links; block content like a list may be written as inline HTML in the cell). Export (`find_details_ids()` + `extract_page_property_divs()`) rewrites the rendered `plugin-tabmeta-details` div back into the directive — reading the `id` from `body.storage` and correlating divs by order — which also removes the rendered copy from the body so `details` is no longer duplicated on round-trip.
  - Page Properties Report (`detailssummary` macro) ↔ `<!-- page-properties-report key=value key="quoted" -->` (each key becomes an `ac:parameter`). Export via `find_report_params()`/`extract_report_macros()` (matches the rendered `metadata-summary-macro` table; handles both `ac:macro` and `ac:structured-macro` storage forms).
  - Passthrough (`extract_unknown_macros`) now also captures legacy top-level `<ac:macro>` elements (`_find_legacy_macros`) so older macros aren't silently dropped. `details`/`detailssummary` are in `KNOWN_MACRO_TYPES` so they're handled by the dedicated logic above, not the generic footer. (Truly arbitrary unknown macros still duplicate on export — there is no reliable anchor for them in `export_view`.)
  - `strip_frontmatter_and_title()` — strips YAML frontmatter and `# Title` heading from markdown before upload
- **`wiki.py`** — export prepends YAML frontmatter (page_id, space, version, author, dates, url) and `# Title`; update/create strip both before uploading. Export replaces Page Properties / Report output with editable directives (token placeholders substituted after html2text)
- **`jira_commands.py`** — `build_jql()` constructs JQL from filter params; `jira-my-tasks` supports `--json` for integrations; `jira-transition` matches by status name (case-insensitive) or transition ID, then posts the resolved id via `set_issue_status_by_transition_id` (the library's `issue_transition`/`set_issue_status` re-resolve the arg as a *status name* and crash on our int id). `--resolution "Won't Do"` sets a resolution during the transition (validated case-insensitively against `get_all_resolutions`, posted as a `fields.resolution` payload; only works on transitions whose screen includes the resolution field); `jira-update` patches individual attributes (summary/description/priority/assignee/type/labels/epic/raw fields). `--label` replaces, `--add-label`/`--remove-label` mutate; pass `--field key=value` with JSON parsing for raw custom fields. Pass `--assignee none` or `--epic none` to clear.
- **`jira_extras.py`** — additional commands inspired by `ankitpokhrel/jira-cli`:
  - `jira-me`, `jira-open` (uses `webbrowser`), `jira-search` (rich JQL + filters, `--csv`/`--json`/`--order-by`/`--reverse`; `--jql` and filters AND together)
  - `jira-comment` / `jira-comments` (add + list comments; `--body` or `--body-file -`)
  - `jira-link` / `jira-unlink` / `jira-link-types` (generic `create_issue_link` with inward/outward keys)
  - `jira-worklog` — `parse_time_spec()` parses Jira time strings (`"1w 2d 3h 30m"`) using `1w=5d, 1d=8h`; bare integers are minutes
  - `jira-sprints` / `jira-sprint-add` / `jira-sprint-issues` (uses Agile API via `get_all_sprints_from_board`/`add_issues_to_sprint`/`get_sprint_issues`)
  - `jira-clone` — copies summary/description/issuetype/priority/labels from source; `--replace find:replace` runs across summary+description
  - `jira-delete` — requires `--yes`; `--cascade` toggles sub-task deletion
  - `jira-epics` (JQL `issuetype = Epic`) / `jira-epic-issues` (tries Agile API first, falls back to JQL on Epic Link field)
- **`cli.py`** — argparse subcommands dispatching to wiki/jira handlers
