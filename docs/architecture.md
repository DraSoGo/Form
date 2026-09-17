# Architecture and implementation contracts

Fitness is a single-user Django 5.2 LTS project using Python 3.12, PostgreSQL 16, Gunicorn, Pillow, Pydantic, httpx, and pywebpush. Server-rendered templates and static JS/CSS contain no frontend secrets. Deployment consists of web, worker, and isolated database services. The web service publishes port `8095` for a trusted LAN; an HTTPS proxy can expose `https://<PUBLIC_HOST>`. The database has no host port.

Packages: config (settings/urls/wsgi), core (profile/body/nutrition/workout models, forms, service functions, auth and views), coaching (AI adapters/context/schema/router, suggestions, chat and durable jobs), core/templates and core/static (mobile UI and PWA). Migrations are committed. Sensitive photos require authenticated views. All mutations POST with CSRF. No public registration.

Core publishes UUID records and documented services for versioned targets/plans. Coaching only creates suggestions; core transactional Accept validates stale before-value and creates a new immutable version. Import has schema/version/reference validation and preview with no overwrite; secrets/sessions excluded.

Provider keys read server environment only. Pool-specific base URL and protocol configuration; no image generation API. Model discovery and text/vision capability tests are explicit; food routing requires confirmed vision. Three candidates maximum and timeouts, no infinite retries. Body triggers deterministic, same-source, minimum observations; chat context bounded.

Scheduler persisted job records with locking/leases, one default daily summary per user-local date; explicit reanalysis creates another version. Push events only for summary/suggestion, no health text on lockscreen. Retention removes photos, preserving entries. Backup uses pg_dump and incremental media, 14 daily/8 weekly archives and isolated restore verification.
