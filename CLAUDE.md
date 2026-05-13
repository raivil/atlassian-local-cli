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
make wiki-create SPACE=<key> TITLE="title" INPUT=<file.md>  # Create Confluence page
make jira-get ISSUE=<key>                                   # Display a Jira issue
make jira-my-tasks [JSON=1] [LIMIT=50]                      # List your assigned tasks
make jira-transition ISSUE=<key> [STATUS="<status>"]        # Transition issue (omit STATUS to list options)
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
uv tool install . --reinstall                               # Install/update globally as `atlassian-local-cli`
```

## Configuration

Env vars loaded from `~/.config/atlassian-local-cli/.env`. See `.env.example`.

- `WIKI_URL` — defaults to `https://wiki.example.com/`
- `WIKI_USERNAME` / `WIKI_TOKEN` — Confluence auth (basic auth when username set, Bearer otherwise)
- `JIRA_URL` / `JIRA_TOKEN` — Jira auth (always Bearer token via PAT)

## Architecture

Python package in `src/atlassian_local_cli/` with `main.py` as a backward-compat shim for PyInstaller. Entry point `atlassian_local_cli.cli:main`. Managed with `uv` and built with `hatchling`.

- **`config.py`** — `Config` dataclass + `get_config()` with lazy loading/caching. `reset_config()` for test isolation.
- **`clients.py`** — `create_confluence()` / `create_jira()` factory functions. Confluence supports basic or Bearer auth; Jira always uses Bearer (PATs don't work with basic auth).
- **`converters.py`** — all pure transformation functions:
  - `preprocess_export_html()` — converts Confluence HTML to markdown tokens before html2text (status badges → `{status:TITLE|colour}`, user mentions → `@username`)
  - `md_to_confluence_html()` — converts markdown to Confluence storage format. Processes status badges and `@username` *before* the markdown parser (to avoid `|` in `{status:X|colour}` breaking table parsing), then transforms `<pre><code>` into `ac:structured-macro` code macros
  - Colspan table section headers: `|| TEXT ||` in markdown ↔ `<th colspan="N">` in Confluence. Column count auto-detected from thead.
  - `strip_frontmatter_and_title()` — strips YAML frontmatter and `# Title` heading from markdown before upload
- **`wiki.py`** — export prepends YAML frontmatter (page_id, space, version, author, dates, url) and `# Title`; update/create strip both before uploading
- **`jira_commands.py`** — `build_jql()` constructs JQL from filter params; `jira-my-tasks` supports `--json` for integrations; `jira-transition` matches by status name (case-insensitive) or transition ID; `jira-update` patches individual attributes (summary/description/priority/assignee/type/labels/epic/raw fields). `--label` replaces, `--add-label`/`--remove-label` mutate; pass `--field key=value` with JSON parsing for raw custom fields. Pass `--assignee none` or `--epic none` to clear.
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
