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

```bash
# View an issue
atlassian-local-cli jira-get PROJ-123

# List your assigned tasks
atlassian-local-cli jira-my-tasks
atlassian-local-cli jira-my-tasks --status closed
atlassian-local-cli jira-my-tasks --type Epic
atlassian-local-cli jira-my-tasks --project PROJ --status open
atlassian-local-cli jira-my-tasks --status-name "Reviewing"
atlassian-local-cli jira-my-tasks --json --limit 10

# Transition an issue
atlassian-local-cli jira-transition PROJ-123                # list available transitions
atlassian-local-cli jira-transition PROJ-123 "In Progress"  # move to status
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
