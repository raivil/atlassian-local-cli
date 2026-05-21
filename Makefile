.PHONY: setup build clean test test-cov wiki-export wiki-update wiki-create jira-create jira-link-epic jira-get jira-my-tasks jira-transition jira-update jira-me jira-open jira-search jira-comment jira-comments jira-link jira-unlink jira-link-types jira-worklog jira-sprints jira-sprint-add jira-sprint-issues jira-clone jira-delete jira-epics jira-epic-issues context-list context-current context-use context-unset context-show

# All atlassian-local-cli invocations. Pass CONTEXT=<name> on any target
# to override the active context just for that command.
CLI = uv run atlassian-local-cli $(if $(CONTEXT),--context $(CONTEXT))

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
	$(CLI) wiki-export $(PAGE) $(if $(OUTPUT),-o $(OUTPUT))

wiki-update: ## Update a wiki page. Usage: make wiki-update PAGE=<page_id> INPUT=<file.md>
	@if [ -z "$(PAGE)" ]; then echo "Error: PAGE is required."; exit 1; fi
	@if [ -z "$(INPUT)" ]; then echo "Error: INPUT is required."; exit 1; fi
	$(CLI) wiki-update $(PAGE) $(INPUT)

wiki-create: ## Create a wiki page. Usage: make wiki-create SPACE=<key> TITLE="<title>" INPUT=<file.md> [PARENT=<page_id>]
	@if [ -z "$(SPACE)" ]; then echo "Error: SPACE is required."; exit 1; fi
	@if [ -z "$(TITLE)" ]; then echo "Error: TITLE is required."; exit 1; fi
	@if [ -z "$(INPUT)" ]; then echo "Error: INPUT is required."; exit 1; fi
	$(CLI) wiki-create $(SPACE) "$(TITLE)" $(INPUT) $(if $(PARENT),--parent $(PARENT))

jira-create: ## Create a Jira issue. Usage: make jira-create PROJECT=<key> SUMMARY="<text>" [TYPE=Task] [PRIORITY=High] [ASSIGNEE=user] [DESCRIPTION="<text>"] [DESC_FILE=<file>]
	@if [ -z "$(PROJECT)" ]; then echo "Error: PROJECT is required."; exit 1; fi
	@if [ -z "$(SUMMARY)" ]; then echo "Error: SUMMARY is required."; exit 1; fi
	$(CLI) jira-create --project $(PROJECT) --summary "$(SUMMARY)" $(if $(TYPE),--type $(TYPE)) $(if $(PRIORITY),--priority $(PRIORITY)) $(if $(ASSIGNEE),--assignee $(ASSIGNEE)) $(if $(DESCRIPTION),--description "$(DESCRIPTION)") $(if $(DESC_FILE),--description-file $(DESC_FILE))

jira-link-epic: ## Link issues to an Epic. Usage: make jira-link-epic ISSUES="PROJ-1 PROJ-2" EPIC=PROJ-100
	@if [ -z "$(ISSUES)" ]; then echo "Error: ISSUES is required."; exit 1; fi
	@if [ -z "$(EPIC)" ]; then echo "Error: EPIC is required."; exit 1; fi
	$(CLI) jira-link-epic $(ISSUES) --epic $(EPIC)

jira-get: ## Get a Jira issue. Usage: make jira-get ISSUE=<key>
	@if [ -z "$(ISSUE)" ]; then echo "Error: ISSUE is required."; exit 1; fi
	$(CLI) jira-get $(ISSUE)

jira-my-tasks: ## List your Jira tasks. Usage: make jira-my-tasks [JSON=1] [LIMIT=50]
	$(CLI) jira-my-tasks $(if $(JSON),--json) $(if $(LIMIT),--limit $(LIMIT))

jira-transition: ## Transition a Jira issue. Usage: make jira-transition ISSUE=<key> [STATUS="<status>"]
	@if [ -z "$(ISSUE)" ]; then echo "Error: ISSUE is required."; exit 1; fi
	$(CLI) jira-transition $(ISSUE) $(STATUS)

jira-me: ## Print the current Jira user
	$(CLI) jira-me $(if $(JSON),--json)

jira-open: ## Open issue in browser. Usage: make jira-open ISSUE=<key>
	@if [ -z "$(ISSUE)" ]; then echo "Error: ISSUE is required."; exit 1; fi
	$(CLI) jira-open $(ISSUE) $(if $(PRINT_URL),--print-url)

jira-search: ## Search Jira. Usage: make jira-search [JQL="..."] [ASSIGNEE=me] [PROJECT=PROJ] [STATUS=open] [TYPE=Bug] [LIMIT=50] [JSON=1] [CSV=1]
	$(CLI) jira-search \
		$(if $(JQL),--jql "$(JQL)") \
		$(if $(ASSIGNEE),--assignee $(ASSIGNEE)) \
		$(if $(REPORTER),--reporter $(REPORTER)) \
		$(if $(STATUS),--status $(STATUS)) \
		$(if $(STATUS_NAME),--status-name "$(STATUS_NAME)") \
		$(if $(TYPE),--type "$(TYPE)") \
		$(if $(PRIORITY),--priority $(PRIORITY)) \
		$(if $(PROJECT),--project $(PROJECT)) \
		$(foreach l,$(LABELS),--label $(l)) \
		$(if $(ORDER_BY),--order-by $(ORDER_BY)) \
		$(if $(REVERSE),--reverse) \
		$(if $(LIMIT),--limit $(LIMIT)) \
		$(if $(JSON),--json) \
		$(if $(CSV),--csv)

jira-comment: ## Add a comment. Usage: make jira-comment ISSUE=<key> BODY="<text>" | BODY_FILE=<file>
	@if [ -z "$(ISSUE)" ]; then echo "Error: ISSUE is required."; exit 1; fi
	$(CLI) jira-comment $(ISSUE) $(if $(BODY),--body "$(BODY)") $(if $(BODY_FILE),--body-file $(BODY_FILE))

jira-comments: ## List comments. Usage: make jira-comments ISSUE=<key>
	@if [ -z "$(ISSUE)" ]; then echo "Error: ISSUE is required."; exit 1; fi
	$(CLI) jira-comments $(ISSUE) $(if $(JSON),--json)

jira-link: ## Link two issues. Usage: make jira-link FROM=<key> TO=<key> TYPE=Blocks [COMMENT="..."]
	@if [ -z "$(FROM)" ] || [ -z "$(TO)" ] || [ -z "$(TYPE)" ]; then echo "Error: FROM, TO, and TYPE are required."; exit 1; fi
	$(CLI) jira-link $(FROM) $(TO) --type "$(TYPE)" $(if $(COMMENT),--comment "$(COMMENT)")

jira-unlink: ## Remove a link. Usage: make jira-unlink LINK_ID=<id>
	@if [ -z "$(LINK_ID)" ]; then echo "Error: LINK_ID is required."; exit 1; fi
	$(CLI) jira-unlink $(LINK_ID)

jira-link-types: ## List link types
	$(CLI) jira-link-types $(if $(JSON),--json)

jira-worklog: ## Log work. Usage: make jira-worklog ISSUE=<key> TIME="2h 30m" [COMMENT="..."]
	@if [ -z "$(ISSUE)" ] || [ -z "$(TIME)" ]; then echo "Error: ISSUE and TIME are required."; exit 1; fi
	$(CLI) jira-worklog $(ISSUE) --time "$(TIME)" $(if $(COMMENT),--comment "$(COMMENT)") $(if $(STARTED),--started "$(STARTED)")

jira-sprints: ## List sprints. Usage: make jira-sprints BOARD=<id> [STATE=active]
	@if [ -z "$(BOARD)" ]; then echo "Error: BOARD is required."; exit 1; fi
	$(CLI) jira-sprints --board $(BOARD) $(if $(STATE),--state $(STATE)) $(if $(JSON),--json)

jira-sprint-add: ## Add issues to sprint. Usage: make jira-sprint-add SPRINT=<id> ISSUES="A-1 A-2"
	@if [ -z "$(SPRINT)" ] || [ -z "$(ISSUES)" ]; then echo "Error: SPRINT and ISSUES are required."; exit 1; fi
	$(CLI) jira-sprint-add $(SPRINT) $(ISSUES)

jira-sprint-issues: ## List sprint issues. Usage: make jira-sprint-issues SPRINT=<id>
	@if [ -z "$(SPRINT)" ]; then echo "Error: SPRINT is required."; exit 1; fi
	$(CLI) jira-sprint-issues $(SPRINT) $(if $(LIMIT),--limit $(LIMIT)) $(if $(JSON),--json)

jira-clone: ## Clone an issue. Usage: make jira-clone ISSUE=<key> [SUMMARY="..."] [REPLACE="old:new ..."]
	@if [ -z "$(ISSUE)" ]; then echo "Error: ISSUE is required."; exit 1; fi
	$(CLI) jira-clone $(ISSUE) $(if $(SUMMARY),--summary "$(SUMMARY)") $(foreach r,$(REPLACE),--replace "$(r)")

jira-delete: ## Delete an issue. Usage: make jira-delete ISSUE=<key> YES=1 [CASCADE=1]
	@if [ -z "$(ISSUE)" ]; then echo "Error: ISSUE is required."; exit 1; fi
	@if [ -z "$(YES)" ]; then echo "Error: YES=1 required to confirm deletion."; exit 1; fi
	$(CLI) jira-delete $(ISSUE) --yes $(if $(CASCADE),--cascade)

jira-epics: ## List epics. Usage: make jira-epics [PROJECT=PROJ] [STATUS=open]
	$(CLI) jira-epics $(if $(PROJECT),--project $(PROJECT)) $(if $(STATUS),--status $(STATUS)) $(if $(LIMIT),--limit $(LIMIT)) $(if $(JSON),--json)

jira-epic-issues: ## List epic children. Usage: make jira-epic-issues EPIC=<key>
	@if [ -z "$(EPIC)" ]; then echo "Error: EPIC is required."; exit 1; fi
	$(CLI) jira-epic-issues $(EPIC) $(if $(LIMIT),--limit $(LIMIT)) $(if $(JSON),--json)

context-list: ## List configured contexts. Active is marked with *.
	$(CLI) context list

context-current: ## Print the currently active context name.
	$(CLI) context current

context-use: ## Set persistent default context. Usage: make context-use NAME=<name>
	@if [ -z "$(NAME)" ]; then echo "Error: NAME is required."; exit 1; fi
	$(CLI) context use $(NAME)

context-unset: ## Clear persistent default context (revert to 'default').
	$(CLI) context unset

context-show: ## Show resolved config for a context. Usage: make context-show [NAME=<name>]
	$(CLI) context show $(NAME)

jira-update: ## Update a Jira issue. Usage: make jira-update ISSUE=<key> [SUMMARY="<text>"] [DESCRIPTION="<text>"] [DESC_FILE=<file>] [PRIORITY=High] [ASSIGNEE=user] [TYPE=Task] [EPIC=PROJ-100] [LABELS="a b"] [ADD_LABELS="a b"] [REMOVE_LABELS="a b"] [FIELDS="key1=val1 key2=val2"]
	@if [ -z "$(ISSUE)" ]; then echo "Error: ISSUE is required."; exit 1; fi
	$(CLI) jira-update $(ISSUE) \
		$(if $(SUMMARY),--summary "$(SUMMARY)") \
		$(if $(DESCRIPTION),--description "$(DESCRIPTION)") \
		$(if $(DESC_FILE),--description-file $(DESC_FILE)) \
		$(if $(PRIORITY),--priority $(PRIORITY)) \
		$(if $(ASSIGNEE),--assignee $(ASSIGNEE)) \
		$(if $(TYPE),--type "$(TYPE)") \
		$(if $(EPIC),--epic $(EPIC)) \
		$(foreach l,$(LABELS),--label $(l)) \
		$(foreach l,$(ADD_LABELS),--add-label $(l)) \
		$(foreach l,$(REMOVE_LABELS),--remove-label $(l)) \
		$(foreach f,$(FIELDS),--field $(f))
