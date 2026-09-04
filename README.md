# atlassian-local-cli

Command-line access to Confluence and Jira. Exports and updates wiki pages as
Markdown, and reads and writes Jira issues, sprints, links and worklogs.

Works with both Atlassian **Cloud** (`*.atlassian.net`) and **Server / Data
Center**.

## Installation

### From source (recommended)

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone <repo-url> && cd atlassian-local-cli
make setup
uv tool install . --reinstall
```

Installs `atlassian-local-cli` into `~/.local/bin/`.

### From binary

Download your platform's binary from the [Releases](../../releases) page:

| Asset | Platform |
|---|---|
| `atlassian-local-cli-macos-arm64` | macOS, Apple Silicon |
| `atlassian-local-cli-macos-x86_64` | macOS, Intel |
| `atlassian-local-cli-linux-x86_64` | Linux, x86_64 |

```bash
chmod +x atlassian-local-cli-*
mv atlassian-local-cli-* /usr/local/bin/atlassian-local-cli
```

## Configuration

Credentials live in `~/.config/atlassian-local-cli/.env`. Create it with
`context add`, which prompts for each value and reads tokens without echoing
them:

```bash
atlassian-local-cli context add default
```

Or write the file by hand, copying `.env.example` as a starting point:

```
WIKI_URL=https://wiki.example.com/
WIKI_USERNAME=your-username
WIKI_TOKEN=your-confluence-token

JIRA_URL=https://jira.example.com/
JIRA_TOKEN=your-jira-token
# JIRA_USERNAME=you@example.com   # Cloud only — see below
```

Verify it with `atlassian-local-cli context show` (tokens are masked).

### Authentication

| Setting | Effect |
|---|---|
| `WIKI_URL` under `*.atlassian.net` | Confluence uses basic auth — **requires `WIKI_USERNAME`** |
| `WIKI_USERNAME` set | Confluence uses basic auth (username + token) |
| Neither | Confluence uses a Bearer token |
| `JIRA_URL` under `*.atlassian.net` | Jira uses basic auth — **requires `JIRA_USERNAME`** |
| Any other `JIRA_URL` | Jira uses a Bearer Personal Access Token |
| `WIKI_AUTH` / `JIRA_AUTH` = `basic`/`bearer` | Overrides the URL rules above |

Cloud and Server reject each other's scheme, so a Cloud URL selects basic auth
on its own. If the matching username is missing, the tool says which key to set
instead of failing with a bare HTTP error.

- **Cloud**: set `WIKI_USERNAME` / `JIRA_USERNAME` to your account email and the
  token to an
  [API token](https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/).
  One API token works for both Jira and Confluence on the same site.
- **Server / Data Center**: set the token to a Personal Access Token and leave
  `JIRA_USERNAME` unset. `WIKI_USERNAME` still selects basic auth here, which is
  how Confluence auth has always been chosen.
- `WIKI_AUTH` / `JIRA_AUTH` are needed only for Cloud on a custom domain, which
  the `*.atlassian.net` check cannot recognise, or to opt an `atlassian.net`
  host out of basic auth.

### Multiple accounts (contexts)

Contexts work like kubectl's. The `.env` above is the `default` context; other
accounts live in `~/.config/atlassian-local-cli/contexts/<name>.env`.

```bash
atlassian-local-cli context add work      # create one, prompting for each value
atlassian-local-cli context list          # list contexts; active is marked *
atlassian-local-cli context current       # print the active context name
atlassian-local-cli context show work     # show resolved config, tokens masked
atlassian-local-cli context use work      # make it the persistent default
atlassian-local-cli context unset         # revert the default to 'default'
```

Use a context for a single command by placing `--context` **before** the
subcommand:

```bash
atlassian-local-cli --context work jira-me
```

Contexts resolve in this order:

1. the `--context` flag
2. the context set by `context use`
3. `default`

Shell environment variables override values from these files, so an exported
`JIRA_TOKEN` in your shell profile defeats every context. `context add` warns
when it detects this.

`context add` takes a flag for each value, which is useful for scripting.
Anything not passed is prompted for, and prompting is skipped when stdin is not
a terminal. Tokens passed as flags are visible in your shell history and in
`ps`:

```bash
atlassian-local-cli context add work \
    --jira-url https://acme.atlassian.net \
    --jira-username me@acme.com \
    --jira-token "$TOKEN"
```

It writes `0600` files and refuses to overwrite an existing context without
`--force`. It does not change the active context.

## Global flags

| Flag | Description |
|---|---|
| `--version`, `-v` | Print the installed version |
| `--context <name>` | Use a named context for this command; must precede the subcommand |

## Usage

### Confluence

```bash
# Export a page to markdown
atlassian-local-cli wiki-export 12345
atlassian-local-cli wiki-export 12345 -o page.md

# Update a page from a markdown file
atlassian-local-cli wiki-update 12345 page.md

# List a page's attachments, or download them
atlassian-local-cli wiki-attachments 12345
atlassian-local-cli wiki-attachments 12345 -o ./attachments
atlassian-local-cli wiki-attachments 12345 -o . --match '*.sql'
atlassian-local-cli wiki-attachments 12345 --json

# Comments (bodies are markdown, converted to Confluence storage format)
atlassian-local-cli wiki-comments 12345
atlassian-local-cli wiki-comments 12345 --location resolved
atlassian-local-cli wiki-comments 12345 --json
atlassian-local-cli wiki-comment 12345 --body "Checked the **replica lag**"
cat notes.md | atlassian-local-cli wiki-comment 12345 --body-file -
atlassian-local-cli wiki-comment-delete 12346 --yes

# Create a new page
atlassian-local-cli wiki-create SPACE "Page Title" content.md
atlassian-local-cli wiki-create SPACE "Page Title" content.md --parent 12345

# Delete a page (moves to trash; --yes is required)
atlassian-local-cli wiki-delete 12345 --yes
atlassian-local-cli wiki-delete 12345 --yes --cascade    # also delete child pages

# Dump raw HTML / list macros (debug a failing or hanging export)
atlassian-local-cli wiki-raw 12345                       # storage format (default)
atlassian-local-cli wiki-raw 12345 --format export       # rendered format
atlassian-local-cli wiki-raw 12345 --format both -o raw.html
atlassian-local-cli wiki-raw 12345 --macros              # list top-level macros
```

Exported files carry YAML frontmatter (page ID, space, version, author, dates,
URL) and a `# Title` heading. Both are stripped automatically on update and
create, so an exported file can be edited and pushed straight back.

`wiki-comment` bodies are markdown and go through the same converter as
`wiki-update`, so lists, code blocks and `**bold**` render properly on the page.
Listing converts the rendered comment HTML back to markdown. `--location`
narrows to `footer`, `inline` or `resolved` comments; replies are indented under
their parent. `wiki-comment-delete` takes a *comment* id (from `wiki-comments`),
requires `--yes`, and refuses an id that turns out to be a page.

`wiki-attachments` lists every attachment on the page (name, size, media type,
version, date); adding `-o <dir>` downloads them into that directory, creating
it if needed. Existing files are overwritten, so re-running picks up newer
versions of an attachment. `--match` takes a shell glob against the filename and
applies to both listing and download. Note that `wiki-export` does not rewrite
attachment links in the markdown to local paths — the exported body still points
at the server.

### Jira

#### View, list, search

```bash
# Print current user
atlassian-local-cli jira-me

# View an issue
atlassian-local-cli jira-get PROJ-123

# Open an issue in your browser
atlassian-local-cli jira-open PROJ-123
atlassian-local-cli jira-open PROJ-123 --print-url       # print URL only

# List your assigned tasks
atlassian-local-cli jira-my-tasks
atlassian-local-cli jira-my-tasks --status closed
atlassian-local-cli jira-my-tasks --project PROJ --status open
atlassian-local-cli jira-my-tasks --status-name "Reviewing"
atlassian-local-cli jira-my-tasks --json --limit 10

# Search — raw JQL, builder flags, or both
atlassian-local-cli jira-search --jql 'project = PROJ AND text ~ "login"'
atlassian-local-cli jira-search --assignee me --status open --type Bug
atlassian-local-cli jira-search --project PROJ --order-by priority --reverse
atlassian-local-cli jira-search --project PROJ --csv > issues.csv
```

#### Create, update, transition

```bash
# Create an issue
atlassian-local-cli jira-create --project PROJ --summary "Fix login" --type Bug --priority High
atlassian-local-cli jira-create --project PROJ --summary "New epic" --type Epic
atlassian-local-cli jira-create --project PROJ --summary "Task" --epic PROJ-100   # under an epic

# Update individual attributes (any combination)
atlassian-local-cli jira-update PROJ-123 --summary "New title"
atlassian-local-cli jira-update PROJ-123 --priority High --assignee jdoe
atlassian-local-cli jira-update PROJ-123 --assignee none              # unassign
atlassian-local-cli jira-update PROJ-123 --epic PROJ-100              # link to epic
atlassian-local-cli jira-update PROJ-123 --epic none                  # unlink epic
atlassian-local-cli jira-update PROJ-123 --label backend --label urgent           # replace
atlassian-local-cli jira-update PROJ-123 --add-label hotfix --remove-label stale  # mutate
atlassian-local-cli jira-update PROJ-123 --description-file notes.md
atlassian-local-cli jira-update PROJ-123 --field 'customfield_10010={"value":"X"}'

# Transition an issue
atlassian-local-cli jira-transition PROJ-123                     # list available transitions
atlassian-local-cli jira-transition PROJ-123 "In Progress"       # by status name or transition ID
atlassian-local-cli jira-transition PROJ-123 Done --resolution "Won't Do"

# Clone, delete
atlassian-local-cli jira-clone PROJ-123 --replace "Q1:Q2"
atlassian-local-cli jira-delete PROJ-123 --yes              # --yes is required
atlassian-local-cli jira-delete PROJ-123 --yes --cascade    # also delete sub-tasks
```

`--resolution` only works on transitions whose screen includes the resolution
field.

#### Comments & worklogs

```bash
# Add and list comments
atlassian-local-cli jira-comment PROJ-123 --body "Looks good to me"
cat notes.md | atlassian-local-cli jira-comment PROJ-123 --body-file -
atlassian-local-cli jira-comments PROJ-123
atlassian-local-cli jira-comments PROJ-123 --json

# Log work (Jira time format: 1w=5d, 1d=8h)
atlassian-local-cli jira-worklog PROJ-123 --time "2h 30m" --comment "Pairing"
atlassian-local-cli jira-worklog PROJ-123 --time "1d"
```

#### Links and epics

```bash
atlassian-local-cli jira-link-types                                       # list link types
atlassian-local-cli jira-link PROJ-1 PROJ-2 --type Blocks                 # PROJ-1 blocks PROJ-2
atlassian-local-cli jira-link PROJ-1 PROJ-2 --type Relates --comment "see this"
atlassian-local-cli jira-unlink 10042                                     # remove link by ID

atlassian-local-cli jira-link-epic PROJ-200 PROJ-201 --epic PROJ-100      # bulk-link to epic
atlassian-local-cli jira-epics --project PROJ                             # list epics
atlassian-local-cli jira-epic-issues PROJ-100                             # list children of epic
```

#### Sprints

```bash
atlassian-local-cli jira-sprints --board 42                       # list sprints on board
atlassian-local-cli jira-sprints --board 42 --state active        # active, closed, future
atlassian-local-cli jira-sprint-add 5 PROJ-1 PROJ-2 PROJ-3        # add issues to sprint
atlassian-local-cli jira-sprint-issues 5                          # list issues in sprint
```

## Reference

### jira-my-tasks filters

| Flag | Description | Example |
|---|---|---|
| `--status` | Status category: `open`, `closed`, `all` | `--status closed` |
| `--status-name` | Exact status name | `--status-name "Reviewing"` |
| `--type` | Issue type | `--type Epic` |
| `--project` | Project key | `--project PROJ` |
| `--limit` | Max results (default: 50) | `--limit 10` |
| `--json` | JSON output, for integrations | `--json` |

### jira-search flags

`jira-search` takes a raw `--jql` clause, the builder filters below, or both.
When both are given they are AND-ed together.

| Flag | Description |
|---|---|
| `--jql` | Raw JQL clause |
| `--assignee` | User key, or `me` / `none` (unassigned) |
| `--reporter` | User key, or `me` |
| `--status` | Status category: `open`, `closed`, `all` |
| `--status-name` | Exact status name (`"In Progress"`) |
| `--type` / `--priority` / `--project` | Exact match |
| `--label` | Repeatable; labels are AND-ed |
| `--order-by` | JQL field to sort by (default: `updated`) |
| `--reverse` | Sort ascending instead of descending |
| `--limit` | Max results (default: 50) |
| `--json` / `--csv` | Machine-readable output |

### jira-update attributes

Pass any combination; only the named fields are changed.

| Flag | Notes |
|---|---|
| `--summary` | Replace the summary |
| `--description` / `--description-file` | Replace description; `-` reads stdin |
| `--priority` | `Highest`, `High`, `Medium`, `Low`, `Lowest` |
| `--assignee` | Username, or `none` to unassign |
| `--type` | Change issue type (e.g. `Bug`) |
| `--epic` | Epic key to link to, or `none` to unlink |
| `--label` | Replace the label set (repeatable) |
| `--add-label` / `--remove-label` | Mutate existing labels (repeatable; cannot mix with `--label`) |
| `--field key=value` | Raw field assignment; values are parsed as JSON when possible |

### Worklog time format

`jira-worklog --time` accepts Jira's work-week syntax. A bare integer is minutes.

| Token | Seconds | Meaning |
|---|---|---|
| `m` | 60 | minute |
| `h` | 3600 | hour |
| `d` | 28800 | day = 8h |
| `w` | 144000 | week = 5d |

Combine tokens freely: `"1w 2d 3h 30m"` or `"2h30m"`.

### Confluence markdown syntax

These forms convert to native Confluence macros on upload, and back to markdown
on export.

| Markdown | Confluence |
|---|---|
| `{status:DONE\|green}` | Status badge |
| `@jdoe` | User mention |
| `{date:2026-03-26}` | Date |
| `{jira:PROJ-123}` | Jira issue link |
| `[TOC]` | Table of contents |
| `<iframe>…</iframe>` | HTML macro (iframe preserved) |
| `> {panel:info\|Title}` + `>` body lines | Info / note / warning / tip / panel macro |
| `<details><summary>Title</summary>` … `</details>` | Expand macro |
| Fenced code blocks | Code macro |
| `\|\| TEXT \|\|` table row | Full-width section header (`colspan`) |
| `<!-- page-properties -->` above a table | Page Properties macro |
| `<!-- page-properties-report key=value -->` | Page Properties Report macro |

Status badge colours: `green`, `red`, `blue`, `yellow`, `grey`.

Panel types: `info`, `note`, `warning`, `tip`, `panel`.

```markdown
| Task         | Status                  | Owner  |
|--------------|-------------------------|--------|
| Deploy DB    | {status:DONE|green}     | @jdoe  |
| Configure LB | {status:PENDING|yellow} | @alice |

> {panel:warning|Heads up}
> This runs against production.
```

### Make targets

Every command is also a make target, for development. Each accepts
`CONTEXT=<name>` to override the active context for that invocation.

```bash
make setup                                                  # Install dependencies
make test                                                   # Run tests
make test-cov                                               # Run tests with coverage
make build                                                  # Build standalone binary
make clean                                                  # Remove build artifacts

make wiki-export PAGE=12345 OUTPUT=page.md
make wiki-update PAGE=12345 INPUT=page.md
make wiki-attachments PAGE=12345 OUTPUT=./attachments MATCH='*.sql'
make wiki-comments PAGE=12345 LOCATION=footer
make wiki-comment PAGE=12345 BODY="Looks right to me"
make wiki-comment-delete COMMENT=12346 YES=1
make wiki-create SPACE=DEV TITLE="My Page" INPUT=page.md
make wiki-delete PAGE=12345 YES=1
make wiki-raw PAGE=12345 FORMAT=storage MACROS=1

make jira-me
make jira-get ISSUE=PROJ-123
make jira-open ISSUE=PROJ-123
make jira-my-tasks JSON=1 LIMIT=10
make jira-search PROJECT=PROJ ASSIGNEE=me CSV=1
make jira-create PROJECT=PROJ SUMMARY="Fix login" TYPE=Bug
make jira-update ISSUE=PROJ-123 PRIORITY=High ASSIGNEE=jdoe
make jira-transition ISSUE=PROJ-123 STATUS="In Progress" RESOLUTION="Won't Do"
make jira-clone ISSUE=PROJ-123 REPLACE="Q1:Q2"
make jira-delete ISSUE=PROJ-123 YES=1
make jira-comment ISSUE=PROJ-123 BODY="LGTM"
make jira-comments ISSUE=PROJ-123
make jira-worklog ISSUE=PROJ-123 TIME="2h 30m"
make jira-link FROM=PROJ-1 TO=PROJ-2 TYPE=Blocks
make jira-unlink LINK_ID=10042
make jira-link-types
make jira-link-epic ISSUES="PROJ-1 PROJ-2" EPIC=PROJ-100
make jira-epics PROJECT=PROJ
make jira-epic-issues EPIC=PROJ-100
make jira-sprints BOARD=42 STATE=active
make jira-sprint-add SPRINT=5 ISSUES="PROJ-1 PROJ-2"
make jira-sprint-issues SPRINT=5

make context-add NAME=work
make context-list
make context-current
make context-show NAME=work
make context-use NAME=work
make context-unset
```

## Development

```bash
make test        # run the test suite
make test-cov    # with coverage, terminal + HTML
make build       # standalone binary at dist/atlassian-local-cli
```

Run a single test:

```bash
uv run pytest tests/test_converters.py::TestMdToConfluenceHtml::test_status_badge
```

## Releasing

Tagging `v*` triggers GitHub Actions, which builds the macOS (arm64, x86_64) and
Linux (x86_64) binaries and publishes a release with them attached.

```bash
# 1. Bump `version` in pyproject.toml and add a CHANGELOG.md entry
# 2. Commit both with the change they describe:
git commit -m "feat: add the thing (v2.9.0)"
# 3. Tag and push:
git tag -s v2.9.0 -m "Release v2.9.0"
git push origin main --follow-tags
```
