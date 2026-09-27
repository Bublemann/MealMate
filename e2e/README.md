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

## Accounts

Every route except `/login`, `/join` and `/reset` needs a signed-in user. The fixtures in
`conftest.py` create accounts through the app itself (plan § 9); all tests of a run share one
database, so names are made unique with `support.api.unique()`.

- `admin`: created once per run with `docker exec <container> mealmate create-admin --username
  admin --display-name Admin --language en --password-stdin` and a random password. With
  `E2E_BASE_URL` there is no container: set `E2E_ADMIN_USERNAME` and `E2E_ADMIN_PASSWORD` to an
  existing admin, otherwise every test that needs an account is skipped.
- `invite_user(username, display_name)`: the admin creates an invite, the user joins with it (API).
- `make_couple(a, b)`: a sends a couple request, b accepts (API).
- `member` / `member_page`: a shared regular user, and `page` signed in as them, for tests that
  only look around. `support.api.sign_in(context, account)` logs a browser context in by storing
  the refresh cookie; `support.ui.log_in()` / `log_out()` go through the screens.
- The app allows 10 requests per minute and IP to `/api/auth/join`, `/reset` and `/codes/check`.
  `support.api.CODE_REQUESTS` counts the suite's own requests and waits when the next ones would
  not fit; a test that opens an invite link in the browser reserves its requests first.

## Conventions

- Find elements by role, accessible name or test ID, never by CSS classes (QA-05). Test IDs are
  read from `frontend/src/testIds.ts` and expected texts from `frontend/src/i18n/*.json`
  (`support/frontend.py`), so the frontend stays the single source of truth.
- Every screen gets an axe check (`support/a11y.py`); serious and critical findings fail.
- `tests/test_privacy.py` asserts that no request leaves the app's origin (SEC-08).
- Reloading offline with a service worker is broken in Playwright WebKit (plan O-11), so that
  test is skipped there. Recheck it on every Playwright upgrade.

## Performance (PERF-02)

`perf/list_p95.py` measures a big list under polling against a running instance, as an
existing user (plan § 9; the M5b gate runs it against the Pi):

```bash
cd e2e && uv run python perf/list_p95.py --base-url https://mealmate.<tailnet>.ts.net \
    --username anna --password-file ~/.mealmate-perf
```

- It creates 20 meals whose rows cover 150 ingredients and a list with all of them (about 155
  lines) and starts shopping (`--draft` polls a draft). Then, for `--rounds` rounds (default
  24), `--interval` seconds apart (default 5), three phones send `GET /api/lists/{id}` with
  `If-None-Match` and a fourth sends a cold GET, one after another spread over the interval
  like independent phones; `--burst` sends all four at the same moment (the worst case). Every
  `--change-every` rounds (default 2) a check-off op changes the list first, so the pollers
  see 200s as well as 304s.
- It prints count, p50, p95 and max for the 200s, the 304s and the ops, and exits with 1 if a
  p95 is above `--threshold-ms` (default 300).
- The list and the meals are deleted afterwards (`--keep` keeps them). The 150 ingredients
  `Perf 000` … `Perf 149` stay in the ingredient wiki (users cannot delete ingredients) and are
  reused by the next run; an admin can delete them.

## Fake Open Food Facts

`fake_off/` is a small FastAPI stand-in for the Open Food Facts API v3 (`uv run uvicorn
fake_off.app:app --port 18081`): it serves `fake_off/fixtures/<barcode>.json` and OFF's
`product_not_found` envelope (404) for every other barcode. It is not wired into the app yet
(milestone M7); fixture `2000000000015` is synthetic (GS1 prefix 2 is for in-store numbers).
