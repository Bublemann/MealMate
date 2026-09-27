# MealMate

A self-hosted web app that turns saved meals into a category-sorted shopping list for fast supermarket trips. It is built for a small household (1–10 people), runs on a Raspberry Pi, and is reachable from anywhere through Tailscale.

> **Status: v2 rewrite in progress.** v1 is archived as the tag `v1-legacy`. What v2 does and how it gets built:
> - [`docs/requirements.md`](docs/requirements.md): what v2 does (requirements with IDs such as `LIST-04`);
> - [`docs/plan.md`](docs/plan.md): architecture, data model and milestones;
> - [`docs/operations.md`](docs/operations.md): running it on the Pi: setup, backups, restore, updates.

## Features (v2)

- Shopping lists built from meals, with servings, sorted by supermarket category.
- Check items off in the store, also offline. Share lists with your partner.
- A shared ingredient database with nutrition values and barcode scanning (Open Food Facts).
- Meals with recipe, photo and source link, plus nutrition per serving.
- German and English UI, installable on the iPhone Home Screen.

## Repository layout

| Path | What |
|---|---|
| `backend/` | FastAPI + SQLAlchemy + Alembic (Python 3.14, managed with `uv`) |
| `frontend/` | React + TypeScript + Vite + Tailwind; see [`frontend/README.md`](frontend/README.md) |
| `e2e/` | End-to-end tests (pytest-playwright) |
| `deploy/` | Production compose file, Raspberry Pi / Mac scripts and their tests; see [`docs/operations.md`](docs/operations.md) |
| `docs/` | Requirements, plan, runbooks |

## Development

Requirements: Docker, [uv](https://docs.astral.sh/uv/), Node.js ≥ 22.12.

```bash
make dev        # backend (auto-reload) + frontend dev server on http://localhost:5173
make test       # backend + frontend tests
make lint       # linters and type checks
make openapi    # regenerate the frontend API types from the backend
make e2e        # build the production image and run the end-to-end tests
make test-deploy  # host scripts against the image (make image first; root and Docker)
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for conventions.

## Licence

[GNU Affero General Public License v3.0 or later](LICENSE). If you run a modified version for others, you must offer them its source code. The app shows a "Source code" link for this purpose.

Nutrition data comes from [Open Food Facts](https://world.openfoodfacts.org) (ODbL).
