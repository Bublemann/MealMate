# End-to-end tests

pytest-playwright tests against the production image, in Chromium and WebKit with an iPhone
profile (QA-04, plan § 9).

```bash
make e2e                                  # build mealmate:e2e, run the suite in Chromium
make e2e E2E_ARGS="--browser webkit"      # the other engine CI runs
cd e2e && uv run playwright install --with-deps chromium webkit   # once, for the browsers
```

## How it runs

- `conftest.py` starts `E2E_IMAGE` (default `mealmate:e2e`) on `127.0.0.1:E2E_PORT` (default
  18080) with an empty in-memory `/data` and the hardening of `deploy/compose.yml`, waits for
  `/api/health` and stops it afterwards. Its log is saved to `test-results/app-container.log`.
- The app runs over plain HTTP with `MEALMATE_COOKIE_SECURE=false`, because WebKit never stores
  `Secure` cookies over HTTP. The production cookie attributes are covered by backend API tests.
- `E2E_BASE_URL=http://…` tests an already running MealMate instead of starting a container.
- Every test runs on an emulated `iPhone 15` with an English locale; `--device "<name>"` picks
  another [Playwright device](https://playwright.dev/python/docs/emulation#devices).
- `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/path/to/chrome` uses a local Chromium build instead of the one
  from `playwright install`.
- Failed tests leave a trace and a screenshot in `test-results/`
  (`uv run playwright show-trace test-results/<test>/trace.zip`).

## Conventions

- Find elements by role, accessible name or test ID, never by CSS classes (QA-05). Test IDs are
  read from `frontend/src/testIds.ts` and expected texts from `frontend/src/i18n/*.json`
  (`support/frontend.py`), so the frontend stays the single source of truth.
- Every screen gets an axe check (`support/a11y.py`); serious and critical findings fail.
- `tests/test_privacy.py` asserts that no request leaves the app's origin (SEC-08).
- Reloading offline with a service worker is broken in Playwright WebKit (plan O-11), so that
  test is skipped there. Recheck it on every Playwright upgrade.

## Fake Open Food Facts

`fake_off/` is a small FastAPI stand-in for the Open Food Facts API v3 (`uv run uvicorn
fake_off.app:app --port 18081`): it serves `fake_off/fixtures/<barcode>.json` and OFF's
`product_not_found` envelope (404) for every other barcode. It is not wired into the app yet
(milestone M7); fixture `2000000000015` is synthetic (GS1 prefix 2 is for in-store numbers).
