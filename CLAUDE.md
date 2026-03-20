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
  - `strip_frontmatter_and_title()` — strips YAML frontmatter and `# Title` heading from markdown before upload
- **`wiki.py`** — export prepends YAML frontmatter (page_id, space, version, author, dates, url) and `# Title`; update/create strip both before uploading
- **`jira_commands.py`** — `build_jql()` constructs JQL from filter params; `jira-my-tasks` supports `--json` for integrations; `jira-transition` matches by status name (case-insensitive) or transition ID
- **`cli.py`** — argparse subcommands dispatching to wiki/jira handlers
