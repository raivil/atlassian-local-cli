.PHONY: setup build clean test test-cov wiki-export wiki-update wiki-create jira-create jira-get jira-my-tasks jira-transition

setup: ## Install dependencies and create venv
	uv sync

build: ## Build standalone binary into dist/
	uv run pyinstaller --onefile --name atlassian-local-cli main.py

clean: ## Remove build artifacts
	rm -rf build dist *.spec htmlcov .coverage

test: ## Run tests
	uv run pytest

test-cov: ## Run tests with coverage report
	uv run pytest --cov=atlassian_local_cli --cov-report=term-missing --cov-report=html

wiki-export: ## Export a wiki page. Usage: make wiki-export PAGE=<page_id> [OUTPUT=<file.md>]
	@if [ -z "$(PAGE)" ]; then echo "Error: PAGE is required."; exit 1; fi
	uv run atlassian-local-cli wiki-export $(PAGE) $(if $(OUTPUT),-o $(OUTPUT))

wiki-update: ## Update a wiki page. Usage: make wiki-update PAGE=<page_id> INPUT=<file.md>
	@if [ -z "$(PAGE)" ]; then echo "Error: PAGE is required."; exit 1; fi
	@if [ -z "$(INPUT)" ]; then echo "Error: INPUT is required."; exit 1; fi
	uv run atlassian-local-cli wiki-update $(PAGE) $(INPUT)

wiki-create: ## Create a wiki page. Usage: make wiki-create SPACE=<key> TITLE="<title>" INPUT=<file.md> [PARENT=<page_id>]
	@if [ -z "$(SPACE)" ]; then echo "Error: SPACE is required."; exit 1; fi
	@if [ -z "$(TITLE)" ]; then echo "Error: TITLE is required."; exit 1; fi
	@if [ -z "$(INPUT)" ]; then echo "Error: INPUT is required."; exit 1; fi
	uv run atlassian-local-cli wiki-create $(SPACE) "$(TITLE)" $(INPUT) $(if $(PARENT),--parent $(PARENT))

jira-create: ## Create a Jira issue. Usage: make jira-create PROJECT=<key> SUMMARY="<text>" [TYPE=Task] [PRIORITY=High] [ASSIGNEE=user] [DESCRIPTION="<text>"] [DESC_FILE=<file>]
	@if [ -z "$(PROJECT)" ]; then echo "Error: PROJECT is required."; exit 1; fi
	@if [ -z "$(SUMMARY)" ]; then echo "Error: SUMMARY is required."; exit 1; fi
	uv run atlassian-local-cli jira-create --project $(PROJECT) --summary "$(SUMMARY)" $(if $(TYPE),--type $(TYPE)) $(if $(PRIORITY),--priority $(PRIORITY)) $(if $(ASSIGNEE),--assignee $(ASSIGNEE)) $(if $(DESCRIPTION),--description "$(DESCRIPTION)") $(if $(DESC_FILE),--description-file $(DESC_FILE))

jira-get: ## Get a Jira issue. Usage: make jira-get ISSUE=<key>
	@if [ -z "$(ISSUE)" ]; then echo "Error: ISSUE is required."; exit 1; fi
	uv run atlassian-local-cli jira-get $(ISSUE)

jira-my-tasks: ## List your Jira tasks. Usage: make jira-my-tasks [JSON=1] [LIMIT=50]
	uv run atlassian-local-cli jira-my-tasks $(if $(JSON),--json) $(if $(LIMIT),--limit $(LIMIT))

jira-transition: ## Transition a Jira issue. Usage: make jira-transition ISSUE=<key> [STATUS="<status>"]
	@if [ -z "$(ISSUE)" ]; then echo "Error: ISSUE is required."; exit 1; fi
	uv run atlassian-local-cli jira-transition $(ISSUE) $(STATUS)
