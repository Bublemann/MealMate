# MealMate developer commands (MNT-03). `make` lists them.
#
# Tools and flags can be overridden per call, e.g. behind a TLS-intercepting proxy (Docker takes
# the value of a bare --build-arg HTTPS_PROXY from the environment):
#   make e2e DOCKER_BUILD_FLAGS="--network host --build-arg HTTPS_PROXY \
#     --secret id=extra_ca,src=/path/to/proxy-ca.crt"

UV ?= uv
NPM ?= npm
DOCKER ?= docker
DOCKER_BUILD_FLAGS ?=
MEALMATE_VERSION ?= 0.0.0-local
MEALMATE_COMMIT ?= $(shell git rev-parse HEAD 2>/dev/null || echo unknown)
E2E_IMAGE ?= mealmate:e2e
E2E_ARGS ?=
DEPLOY_TEST_IMAGE ?= mealmate:local
DEPLOY_TEST_ARGS ?=
SHELLCHECK_IMAGE ?= koalaman/shellcheck:v0.11.0@sha256:bb596a0d169b85ddd81d8b6d3a2ff6d5baf5fca10b97f575ebc647c3dff62b3d
DEPLOY_SCRIPTS = deploy/pi/setup.sh deploy/pi/bin/mm-compose deploy/pi/bin/backup.sh \
	deploy/pi/bin/update.sh deploy/pi/bin/heartbeat.sh deploy/pi/bin/disk-check.sh \
	deploy/mac/install-backup-pull.sh deploy/mac/pull.sh

BUILD = $(DOCKER) buildx build $(DOCKER_BUILD_FLAGS) \
	--build-arg MEALMATE_VERSION=$(MEALMATE_VERSION) --build-arg MEALMATE_COMMIT=$(MEALMATE_COMMIT)

.DEFAULT_GOAL := help
.PHONY: help dev test test-backend test-frontend test-deploy lint lint-backend lint-frontend \
	lint-e2e lint-deploy openapi image e2e

help: ## List the commands
	@awk 'BEGIN { FS = ":.*## " } /^[a-z0-9-]+:.*## / { printf "  make %-14s %s\n", $$1, $$2 }' \
		$(MAKEFILE_LIST)

dev: ## Full stack with hot reload on http://localhost:5173
	$(DOCKER) compose -f compose.dev.yml up --build

test: test-backend test-frontend ## Backend and frontend tests

test-backend: ## Backend tests with the coverage gate (pytest)
	cd backend && $(UV) run pytest

test-frontend: ## Frontend tests (Vitest)
	$(NPM) --prefix frontend run test

lint: lint-backend lint-frontend lint-e2e lint-deploy ## Linters, formatting and type checks

lint-backend: ## ruff, ruff format, mypy
	cd backend && $(UV) run ruff check . && $(UV) run ruff format --check . && $(UV) run mypy app

lint-frontend: ## eslint, prettier, tsc
	$(NPM) --prefix frontend run lint
	$(NPM) --prefix frontend run format
	$(NPM) --prefix frontend run typecheck

lint-e2e: ## ruff and ruff format on the end-to-end suite
	cd e2e && $(UV) run ruff check . && $(UV) run ruff format --check .

lint-deploy: ## shellcheck on the host and Mac scripts, ruff on the deploy tests and prune.py
	$(DOCKER) run --rm -v "$(CURDIR):/mnt" -w /mnt $(SHELLCHECK_IMAGE) -x $(DEPLOY_SCRIPTS)
	cd deploy/tests && $(UV) run ruff check . ../common && $(UV) run ruff format --check . ../common

openapi: ## Regenerate frontend/src/api/generated/ from the backend
	cd backend && $(UV) run mealmate export-openapi ../frontend/src/api/generated/openapi.json
	$(NPM) --prefix frontend run openapi:types

image: ## Build the production image as mealmate:local
	$(BUILD) --load -t mealmate:local .

test-deploy: ## Deploy tests against DEPLOY_TEST_IMAGE (make image first; needs root and Docker)
	cd deploy/tests && MEALMATE_TEST_IMAGE=$(DEPLOY_TEST_IMAGE) $(UV) run pytest $(DEPLOY_TEST_ARGS)

e2e: ## Build mealmate:e2e and run the end-to-end suite (E2E_ARGS="--browser webkit")
	$(BUILD) --load -t $(E2E_IMAGE) .
	cd e2e && E2E_IMAGE=$(E2E_IMAGE) $(UV) run pytest $(E2E_ARGS)
