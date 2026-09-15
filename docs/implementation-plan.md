# Fitness implementation plan

Goal: implement the complete requirements in requirements.md, deploy safely, and verify each phase.
Architecture: see architecture.md. Skills: subagent-driven-development for independently reviewable implementation tasks; root coordinates integration and deployment. User explicitly authorized continuous execution without phase gates.

- [x] Phase 0: read-only infrastructure audit; document blocked privileged checks.
- [ ] Phase 1: core Django foundation, authenticated forms, validated domain models and migrations; tests for sessions/CSRF/rate limits/body/targets/plans/sets/import.
- [ ] Phase 2: nutrition/workout/mobile interfaces, food memory/media retention, charts, PWA timer; integration/browser checks.
- [ ] Phase 3: AI adapters/schema/context/router, versioned suggestions and chat, scheduler and push; mocked provider tests, no paid calls in suite.
- [ ] Phase 4: build isolated Compose stack, secrets generation outside source, NAS backup job with retention and isolated PostgreSQL/media restore test.
- [ ] Phase 5: public HTTPS if permissions available, preserve existing routes, end-to-end verification and regression checks; docs and sensible commits.

Core implementation task owns config/, core/, manage.py, dependencies and templates. AI implementation task owns coaching/ and its tests/templates, integrating via documented core interfaces. Ops task owns Dockerfile, compose.yaml, ops/, deployment and recovery docs. Review completed tasks and run tests before deploying. Every requirement in requirements.md is an acceptance criterion; report unchecked items honestly.

Tests: `python manage.py test` (isolated test database), `python manage.py check --deploy`, migrations check, mocked AI failover and malformed-output tests; browser login/CRUD/workout/retention/export/import; `ops/backup.sh` then `ops/restore-test.sh` against own Compose database only. Normal tests never send user health data or make AI calls. Live smoke command separately verifies only new configured keys.
