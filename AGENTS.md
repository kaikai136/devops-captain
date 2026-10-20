# Repository Guidelines

## Project Structure & Module Organization

- `backend/` contains Django apps, REST APIs, and Channels services. Settings live in `ops_tool/`; database tools in `database_management/`; SSH/RDP functionality in `web_terminal/`.
- `frontend/src/` contains Vue 3 and TypeScript: `app/` handles orchestration, `features/` domain modules, `shared/` reusable code, and `components/tools/` management pages. Preserve compatibility re-exports in older `composables/` paths.
- Frontend assets live in `frontend/public/` and `frontend/src/assets/`; styles in `frontend/src/styles/`. Deployment files, configuration, and documentation live in `deploy/`, `config/`, and `docs/`.

## Build, Test, and Development Commands

Run frontend commands from `frontend/`:

- `npm ci` installs locked dependencies.
- `npm run dev` starts Vite with API/WebSocket proxies.
- `npm run build` generates the production bundle in `dist/`.
- `npm run test:run` runs Vitest once; `npm test` enables watch mode.

Run backend commands from `backend/` in an activated virtual environment; use Django 5.x as constrained by `requirements.txt`. Linux/WSL is recommended.

- `python -m pip install -r requirements.txt` installs dependencies.
- `python manage.py migrate` applies schema migrations.
- `python -m daphne -b 0.0.0.0 -p 8001 ops_tool.asgi:application` starts API/WebSocket services.
- `python manage.py run_database_transfer_worker --poll-interval 1` starts the separate import/export worker; Redis must be available.
- `python manage.py test database_management accounts` runs targeted backend tests.

## Coding Style & Naming Conventions

Use four-space Python and two-space Vue/TypeScript indentation. Match neighboring TypeScript single quotes and semicolons. Name components `PascalCase.vue`, composables `useSomething.ts`, and Python modules/functions `snake_case`. Prefer feature-local helpers over expanding page components. No dedicated ESLint or Prettier configuration is present.

## Testing Guidelines

Use Vitest `*.test.ts` files under `src/**/__tests__/` and Django `TestCase`/`SimpleTestCase` with `test_*` methods. Add behavioral regressions and preserve structure contracts. No coverage threshold is configured. Legacy `frontend/tests/*.test.mjs` use Node's test runner separately; some require generated helpers. Run relevant tests and the frontend build before review.

## Commit & Pull Request Guidelines

Follow existing `fix:`, `feat:`, and `refactor:` prefixes with concise descriptions. Keep commits focused. PRs should explain behavior changes, link issues, report validation, and include screenshots for UI changes. Highlight migrations and configuration changes.

## Security & Configuration

Use `APP_CONFIG_FILE` for backend configuration and `config/local.app.conf` for Vite settings. API and workers must share Redis configuration. Use `deploy/config/app.conf` as the deployment template. Never commit credentials, databases, recordings, or runtime files; never log plaintext secrets.
