# Repository Guidelines

## Project Structure & Module Organization

Form is a Django application. `config/` contains project settings, URL routing, and WSGI setup. `core/` owns fitness, nutrition, body, and workout features; `coaching/` contains AI routing, background jobs, and coaching views. Keep templates and browser assets under each app's `templates/` and `static/` directories. Database migrations live in `<app>/migrations/`. Operational backup code and systemd units belong in `ops/`; architecture, deployment, security, and recovery notes belong in `docs/`. Treat `staticfiles/` as generated output.

## Build, Test, and Development Commands

Run commands from the repository root:

```sh
.venv/bin/pip install -r requirements.lock
SECRET_KEY=test-only USE_SQLITE=1 SECURE_COOKIES=false .venv/bin/python manage.py runserver
SECRET_KEY=test-only USE_SQLITE=1 SECURE_COOKIES=false .venv/bin/python manage.py test
.venv/bin/python -m unittest discover -s ops -p 'test_*.py' -v
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py check
docker compose build
docker compose up -d db web worker
```

Use SQLite for local application tests. The Compose stack mirrors production with PostgreSQL, Gunicorn, and a separate worker.

## Coding Style & Naming Conventions

Use four-space indentation in Python. Name modules, functions, and variables with `snake_case`; use `PascalCase` for Django models, forms, and test classes. Keep views thin and place domain behavior in `services.py` or focused modules. Follow the surrounding file's quote and layout style because the repository does not pin a formatter. Generate schema changes with Django migrations; do not edit migration history after deployment.

## Testing Guidelines

Write Django tests in `tests.py` or `test_*.py` using `TestCase` or `SimpleTestCase`. Name methods `test_<behavior>`. Put backup-tool tests in `ops/test_*.py`. Mock AI providers and external requests; tests must not send health data or use live credentials. Add regression coverage for authorization, ownership boundaries, validation, migrations, and destructive operations.

## Commit & Pull Request Guidelines

History uses short Conventional Commit subjects such as `feat: add cardio tracking`, `fix: allow mobile uploads`, and `docs: record deployment`. Keep each commit focused. Pull requests should explain the user-visible change, list verification commands, call out migrations or configuration changes, and include screenshots for UI work. Link the relevant issue or design document when one exists.

## Security & Configuration

Copy `.env.example` into the protected server runtime file; never commit secrets, databases, media, or provider responses. Review `docs/security.md` and `docs/backup-restore.md` before changing authentication, imports, backups, network exposure, or AI data flow.
