# Contributing to MealMate

What to build is defined in [`docs/requirements.md`](docs/requirements.md); how and in which order is in [`docs/plan.md`](docs/plan.md). Reference requirement IDs (e.g. `LIST-04`) in pull requests and tests.

## Workflow

- `main` is the integration branch. Work on a short-lived branch and open a pull request. CI must be green.
- Branch names say what the branch is about:

  | Prefix | For | Example |
  |---|---|---|
  | `feature/` | new functionality | `feature/v2-accounts`, `feature/barcode-scanner` |
  | `fix/` | bug fixes | `fix/list-rounding` |
  | `docs/` | documentation only | `docs/operations-runbook` |
  | `chore/` | tooling, dependencies, CI | `chore/bump-node-24` |
  | `release/X.Y` | release lines (created by the release workflow) | `release/2.0` |
  | `hotfix/` | fixes branched from and merged back into `release/X.Y` | `hotfix/2.0-login-timeout` |
- PR titles use [Conventional Commits](https://www.conventionalcommits.org/): `feat: …`, `fix: …`, `docs: …`, `chore: …`, `test: …`, `refactor: …`. Feature PRs are **squash-merged**, so the PR title becomes the changelog entry.
- Releases are cut from `release/X.Y` branches. Sync PRs (`main → release/X.Y`) and back-merge PRs (`release/X.Y → main`) use **merge commits**, never squash. Details: plan § 10.
- Never commit secrets, keys, certificates, databases or `.env` files. CI runs a secret scanner.

## Architecture rules

1. **The backend owns the logic.** Amounts, conversions, aggregation, rounding, nutrition and permissions live in `backend/app/domain` and `backend/app/services`. The frontend only formats and displays.
2. **The API contract is generated.** Every endpoint has a `response_model`, and the frontend's TypeScript types are generated from OpenAPI (`make openapi`). CI fails if they are stale.
3. **No user-facing text from the backend.** Errors are codes (`ErrorCode`) that the frontend translates (`error.<code>` in `de.json`/`en.json`).
4. **Layers in the backend:** `api/` (HTTP only) → `services/` (rules, permissions, transactions) → `repositories/` (queries) → `models/`. `domain/` is pure Python without I/O.
5. **Frontend conventions:** see [`frontend/README.md`](frontend/README.md): i18n keys for every string, API calls only through `src/api/`, test IDs from `src/testIds.ts`, UI building blocks in `src/components/ui/`.
6. **Host scripts** (`deploy/`): bash with `set -euo pipefail`, shellcheck-clean (`make lint-deploy`), idempotent; Mac scripts stay bash 3.2 compatible. Never write through a path in the container-writable `data/`. Covered by `deploy/tests/` (`make test-deploy`); the owner's runbook is [`docs/operations.md`](docs/operations.md).

## Checklists for common extensions

| Adding… | Steps |
|---|---|
| a translation string | add the key to **both** `frontend/src/i18n/de.json` and `en.json` (the completeness test enforces this) |
| an error code | add it to `ErrorCode` in `backend/app/core/errors.py`, run `make openapi`, then add `error.<code>` to both language files |
| a language | add `frontend/src/i18n/<lang>.json`; in `frontend/src/i18n/index.ts` add the code to `LANGUAGES`, its own name to `LANGUAGE_NAMES` and the file to `resources`; add its `Intl` locale to `LOCALES` in `frontend/src/i18n/format.ts`; add it to the backend's `language` enum; add its category name columns (`name_<lang>`, `name_<lang>_norm`) to the `Category` model, with a migration that adds them empty, its field to `CategoryNames` and its name to the category functions in `backend/app/services/reference.py` (plan § 6; the English names show until admins fill them in). The completeness test picks up the new file by itself (details: [`frontend/README.md`](frontend/README.md#translations)) |
| a nutrient | add it to the nutrients registry (`backend/app/domain/nutrients.py`), `alembic revision --autogenerate`, add translation keys and OFF mapping tests |
| a cuisine / unit conversion | add a migration that seeds it, then translation keys `cuisine.<key>` / `unit.<unit>`. Categories are data, not code: admins add, rename and delete them on the admin screen (REF-01) |
| a database change | edit the models, run `alembic revision --autogenerate -m "…"`, review the migration, and make sure the migration tests pass (they also run against a populated database) |

## Local commands

```bash
make dev          # full stack with hot reload
make test         # backend (pytest, coverage ≥ 85 %) + frontend (vitest)
make lint         # ruff, mypy, eslint, prettier, tsc
make openapi      # regenerate frontend/src/api/generated/*
make e2e          # production image + end-to-end tests
```
