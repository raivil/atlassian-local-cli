# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

CLI tool (`atlassian-local-cli`) for interacting with Confluence and Jira. Uses `atlassian-python-api` for API calls, `html2text` for HTML→MD export, and `markdown` for MD→HTML upload.

## Commands

```bash
make setup                                                  # Install dependencies (uv sync)
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

Single-file CLI (`main.py`) with argparse subcommands. Entry point `main()` registered as `atlassian-local-cli` in `pyproject.toml`. Managed with `uv`.

- `_confluence()` / `_jira()` — build authenticated client instances. Confluence supports basic or Bearer auth; Jira always uses Bearer (PATs don't work with basic auth)
- `_md_to_confluence_html()` — converts markdown to Confluence storage format; transforms `<pre><code>` into `ac:structured-macro` code macros for proper syntax highlighting
- `_unescape_html()` — reverses HTML entity encoding inside code blocks before wrapping in CDATA
- Export prepends a `# Title` heading; update/create strip it before uploading
- `jira-my-tasks` supports `--json` for integration use and table format for terminal
- `jira-transition` matches by status name (case-insensitive) or transition ID
