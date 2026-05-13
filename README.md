# atlassian-local-cli

CLI tool for interacting with Confluence and Jira from the terminal.

## Installation

### From source (recommended)

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone <repo-url> && cd atlassian-local-cli
make setup
uv tool install . --reinstall
```

This installs `atlassian-local-cli` globally in `~/.local/bin/`.

### From binary

Download the latest binary from the [Releases](../../releases) page for your platform:

- `atlassian-local-cli-macos-arm64` — macOS Apple Silicon
- `atlassian-local-cli-macos-x86_64` — macOS Intel
- `atlassian-local-cli-linux-x86_64` — Linux

```bash
chmod +x atlassian-local-cli-*
mv atlassian-local-cli-* /usr/local/bin/atlassian-local-cli
```

## Configuration

Create the config file:

```bash
mkdir -p ~/.config/atlassian-local-cli
cp .env.example ~/.config/atlassian-local-cli/.env
```

Edit `~/.config/atlassian-local-cli/.env` with your credentials:

```
WIKI_URL=https://wiki.example.com/
WIKI_USERNAME=your-username
WIKI_TOKEN=your-confluence-token

JIRA_URL=https://jira.example.com/
JIRA_TOKEN=your-jira-personal-access-token
```

**Auth modes:**
- **Confluence**: basic auth (username + token) when `WIKI_USERNAME` is set, Bearer token otherwise
- **Jira**: always uses Bearer token (Personal Access Tokens)

## Usage

### Confluence

```bash
# Export a page to markdown
atlassian-local-cli wiki-export 12345
atlassian-local-cli wiki-export 12345 -o page.md

# Update a page from a markdown file
atlassian-local-cli wiki-update 12345 page.md

# Create a new page
atlassian-local-cli wiki-create SPACE "Page Title" content.md
atlassian-local-cli wiki-create SPACE "Page Title" content.md --parent 12345
```

### Jira

#### View, list, search

```bash
# Print current user
atlassian-local-cli jira-me

# Open an issue in your browser
atlassian-local-cli jira-open PROJ-123
atlassian-local-cli jira-open PROJ-123 --print-url       # print URL only

# View an issue
atlassian-local-cli jira-get PROJ-123

# List your assigned tasks
atlassian-local-cli jira-my-tasks
atlassian-local-cli jira-my-tasks --status closed
atlassian-local-cli jira-my-tasks --type Epic
atlassian-local-cli jira-my-tasks --project PROJ --status open
atlassian-local-cli jira-my-tasks --status-name "Reviewing"
atlassian-local-cli jira-my-tasks --json --limit 10

# Rich search — raw JQL or builder flags
atlassian-local-cli jira-search --jql 'project = PROJ AND text ~ "login"'
atlassian-local-cli jira-search --assignee me --status open --type Bug
atlassian-local-cli jira-search --reporter me --priority High --label backend
atlassian-local-cli jira-search --project PROJ --order-by priority --reverse
atlassian-local-cli jira-search --project PROJ --csv > issues.csv
```

#### Create, update, transition

```bash
# Create an issue
atlassian-local-cli jira-create --project PROJ --summary "Fix login" --type Bug --priority High --assignee jdoe
atlassian-local-cli jira-create --project PROJ --summary "New epic" --type Epic
atlassian-local-cli jira-create --project PROJ --summary "Sub-task" --epic PROJ-100

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
atlassian-local-cli jira-transition PROJ-123                # list available transitions
atlassian-local-cli jira-transition PROJ-123 "In Progress"  # move to status

# Clone, delete
atlassian-local-cli jira-clone PROJ-123 --replace "Q1:Q2"
atlassian-local-cli jira-delete PROJ-123 --yes              # --yes is required
atlassian-local-cli jira-delete PROJ-123 --yes --cascade    # also delete sub-tasks
```

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

#### Links

```bash
atlassian-local-cli jira-link-types                                       # list available link types
atlassian-local-cli jira-link PROJ-1 PROJ-2 --type Blocks                 # PROJ-1 blocks PROJ-2
atlassian-local-cli jira-link PROJ-1 PROJ-2 --type Relates --comment "see this"
atlassian-local-cli jira-unlink 10042                                     # remove link by ID

# Epic-specific helpers
atlassian-local-cli jira-link-epic PROJ-200 PROJ-201 --epic PROJ-100      # bulk-link to epic
atlassian-local-cli jira-epics --project PROJ                             # list epics
atlassian-local-cli jira-epic-issues PROJ-100                             # list children of epic
```

#### Sprints

```bash
atlassian-local-cli jira-sprints --board 42                       # list sprints on board
atlassian-local-cli jira-sprints --board 42 --state active
atlassian-local-cli jira-sprint-add 5 PROJ-1 PROJ-2 PROJ-3        # add issues to sprint
atlassian-local-cli jira-sprint-issues 5                          # list issues in sprint
```

### jira-my-tasks filters

| Flag | Description | Example |
|---|---|---|
| `--status` | Filter by category: `open`, `closed`, `all` | `--status closed` |
| `--status-name` | Filter by exact status name | `--status-name "Reviewing"` |
| `--type` | Filter by issue type | `--type Epic` |
| `--project` | Filter by project key | `--project PROJ` |
| `--limit` | Max results (default: 50) | `--limit 10` |
| `--json` | Output as JSON for integrations | `--json` |

### jira-search flags

`jira-search` accepts a raw `--jql` clause and/or any of the builder filters below. When both are given they are AND-ed together.

| Flag | Description |
|---|---|
| `--jql` | Raw JQL clause (combined with filters via `AND`) |
| `--assignee` | User key, or `me`/`none` (unassigned) |
| `--reporter` | User key, or `me` |
| `--status` | `open` / `closed` / `all` (by status category) |
| `--status-name` | Exact status name (`"In Progress"`) |
| `--type` / `--priority` / `--project` | Exact match |
| `--label` | Repeatable; each label is AND-ed |
| `--order-by` | JQL field to sort by (default: `updated`) |
| `--reverse` | Sort ascending instead of descending |
| `--limit` | Max results (default: 50) |
| `--json` / `--csv` | Machine-readable output |

### jira-update attributes

Pass any combination of flags to PATCH only those fields.

| Flag | Notes |
|---|---|
| `--summary` | Replace the issue summary |
| `--description` / `--description-file` | Replace description; `-` reads stdin |
| `--priority` | `Highest`, `High`, `Medium`, `Low`, `Lowest` |
| `--assignee` | Username, or `none` to unassign |
| `--type` | Change issue type (e.g. `Bug`) |
| `--epic` | Epic key to link to, or `none` to unlink |
| `--label` | Replace label set (repeatable) |
| `--add-label` / `--remove-label` | Mutate existing labels (repeatable, cannot mix with `--label`) |
| `--field key=value` | Raw field assignment; values are parsed as JSON when possible |

### Worklog time format

`jira-worklog --time` accepts Jira's standard work-week syntax. A bare integer is treated as minutes.

| Token | Seconds | Notes |
|---|---|---|
| `m` | 60 | minute |
| `h` | 3600 | hour |
| `d` | 28800 | day = 8h |
| `w` | 144000 | week = 5d |

Combine tokens freely: `"1w 2d 3h 30m"` or `"2h30m"`.

### Confluence-specific syntax

Status badges and user mentions are supported in markdown and convert to/from native Confluence macros:

```markdown
| Task         | Status              | Owner    |
|--------------|---------------------|----------|
| Deploy DB    | {status:DONE|green} | @jdoe    |
| Configure LB | {status:PENDING|yellow} | @alice |
```

**Status badge colours:** `green`, `red`, `blue`, `yellow`, `grey`

### Make targets

All commands are also available as make targets for development:

```bash
make setup                                                  # Install dependencies
make test                                                   # Run tests
make test-cov                                               # Run tests with coverage
make build                                                  # Build standalone binary
make clean                                                  # Remove build artifacts
make wiki-export PAGE=12345 OUTPUT=page.md
make wiki-update PAGE=12345 INPUT=page.md
make wiki-create SPACE=DEV TITLE="My Page" INPUT=page.md
make jira-get ISSUE=PROJ-123
make jira-my-tasks JSON=1 LIMIT=10
make jira-transition ISSUE=PROJ-123 STATUS="In Progress"
make jira-update ISSUE=PROJ-123 PRIORITY=High ASSIGNEE=jdoe
make jira-search PROJECT=PROJ ASSIGNEE=me CSV=1
make jira-comment ISSUE=PROJ-123 BODY="LGTM"
make jira-comments ISSUE=PROJ-123
make jira-link FROM=PROJ-1 TO=PROJ-2 TYPE=Blocks
make jira-worklog ISSUE=PROJ-123 TIME="2h 30m"
make jira-sprints BOARD=42 STATE=active
make jira-sprint-add SPRINT=5 ISSUES="PROJ-1 PROJ-2"
make jira-clone ISSUE=PROJ-123 REPLACE="Q1:Q2"
make jira-delete ISSUE=PROJ-123 YES=1
make jira-epics PROJECT=PROJ
make jira-epic-issues EPIC=PROJ-100
make jira-me
make jira-open ISSUE=PROJ-123
```

## Building

```bash
make build
```

Produces a standalone binary at `dist/atlassian-local-cli`.

## Releasing

Automated builds for macOS (arm64, x86_64) and Linux (x86_64) run via GitHub Actions on tagged releases.

```bash
# Update version in pyproject.toml, then:
git add pyproject.toml
git commit -m "Bump version to 0.3.0"
git tag v0.3.0
git push origin main --tags
```

This triggers the CI pipeline which builds binaries for all platforms and creates a GitHub release with the artifacts attached.
