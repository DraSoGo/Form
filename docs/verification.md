# Verification record

Verified on 2026-09-16 against commit `2851b3852bb74b40eaff8b6ace01e871c023e779`.

Status meanings:

- **Pass:** verified by a focused test, a production check, or both.
- **Conditional:** implementation and failure behavior are verified, but a fresh external credential or physical device is required for a live provider check.

| Check | Status | Evidence |
|---|---|---|
| 1. Login works. | Pass | Production HTTPS login returned the dashboard and issued a secure session cookie. |
| 2. Wrong password is rejected/rate-limited. | Pass | Production rejected a wrong password; automated tests verify attempt limits, expiry, and successful-login reset. |
| 3. Body metrics can be created and updated. | Pass | PostgreSQL flow test verifies create and edit. |
| 4. Historical metrics remain intact. | Pass | Flow test verifies other measurements remain unchanged after an edit. |
| 5. Nutrition target works. | Pass | Versioning, validation, stale-write protection, and rendering tests pass. |
| 6. Manual food entry works. | Pass | Flow test verifies entry, totals, and reuse. |
| 7. Food photo upload works. | Pass | Upload test verifies MIME checks, size handling, decoding, and safe re-encoding. |
| 8. AI food analysis works or clearly reports provider capability failure. | Pass | Live MaxPlus vision calls analyzed both pending production photos with `gpt-5.6-sol`; both entries now contain estimated nutrients and uncertainty. |
| 9. User correction works. | Pass | Correction test verifies totals change without creating a duplicate entry. |
| 10. Saved food works. | Pass | Food library and meal-template snapshot tests pass. |
| 11. Workout plan works. | Pass | Plan validation, versioning, stale-write protection, and populated-page rendering pass. |
| 12. Fixed schedule works. | Pass | Weekday selection test passes. |
| 13. Rotation works. | Pass | Rotation advances only after a finished workout and handles rest days. |
| 14. Workout session works. | Pass | Session creation, plan snapshot, and completion tests pass. |
| 15. Set logging works. | Pass | Planned-set, actual-set, and completion tests pass. |
| 16. Rest Timer works. | Pass | Timer UI and populated workout page render in the mobile flow. |
| 17. Copy Last Session works. | Pass | Flow test verifies actual values copy while completion resets. |
| 18. Weekly volume calculations work. | Pass | Test verifies completed work plus indirect-muscle volume rules. |
| 19. Cardio log works. | Pass | Populated core-page flow and archive round-trip tests pass. |
| 20. Sleep log works. | Pass | Populated core-page flow and bounded coaching-context tests pass. |
| 21. Coach Chat works. | Pass | Authentication, schema, suggestion-only persistence, and failure tests pass; a live structured MaxPlus chat response also passed validation. |
| 22. Suggested Change works. | Pass | Validation and persistence tests pass. |
| 23. Accept creates a new version. | Pass | Acceptance test verifies a new immutable version. |
| 24. Reject preserves current version. | Pass | Rejection test verifies no version change. |
| 25. Daily Summary can run manually. | Pass | Job creation, idempotency, context, output persistence, and a live structured MaxPlus daily response passed. |
| 26. Scheduled summary works. | Conditional | Bangkok date/time scheduling and worker behavior pass tests; the production worker and verified live model are running. The next wall-clock scheduled execution has not yet been observed. |
| 27. Re-analyze creates another summary version. | Pass | Versioning test passes. |
| 28. AI provider fallback works. | Pass | Bounded one-step failover and model-disable tests pass with mocked provider responses. |
| 29. Retry after all providers fail works. | Pass | Retry test verifies no failed output is persisted and the job can run again. |
| 30. PWA installs. | Conditional | Manifest, service worker, icons, secure public origin, and mobile layout were verified. Native installation confirmation needs a supported physical browser. |
| 31. Push notification works. | Conditional | VAPID keys are configured; subscribe, revoke, validation, and send-path tests pass. A physical browser subscription was not available for delivery confirmation. |
| 32. Food retention setting works. | Pass | Test verifies only expired image data is removed. |
| 33. CSV export works. | Pass | Export test verifies zero/false retention and spreadsheet-formula neutralization. |
| 34. JSON export works. | Pass | Full archive round-trip test passes and excludes image bytes. |
| 35. JSON validation/import works. | Pass | Schema, references, uniqueness, nulls, semantics, ownership, timestamps, and inert imported jobs are tested. |
| 36. Backup job works. | Pass | Real NAS backup `20260916T092015Z-ce34adb5` completed, verified checksums, and recorded success. Daily timer is enabled. |
| 37. Restore test succeeds. | Pass | Real dump restored into an isolated PostgreSQL database; schema semantics, migrations, table counts, and media matched. Weekly timer is enabled. |
| 38. `/health` works. | Pass | Production loopback health endpoint returned `{"status":"ok"}`. |
| 39. Existing server applications still work. | Pass | Existing 21 containers remained running. OJ, Nextcloud, Immich, Paperless, Homepage, Kuma, and Beszel HTTP checks returned 200 after deployment. |
| 40. Public HTTPS access works using the chosen safe mechanism. | Pass | Tailscale Funnel serves Fitness at `https://hp800-g5.tail985cfd.ts.net:8443`; secure-cookie, HSTS, CSP, no-store, and MIME-protection headers were verified. Existing port 443 route remains unchanged. |

## Automated suites

- Django: 70 tests passed on SQLite; the prior 68-test suite also passed on isolated PostgreSQL before the two HTML spacing regressions were added.
- Operations: 12 tests passed.
- Production deployment check passed. Django reports only the intentional shared-domain HSTS subdomain/preload warnings.

## Backup schedule

- Daily backup: 03:30 server local time, with up to 15 minutes randomized delay.
- Weekly isolated restore: Sunday 05:00 server local time, with up to 15 minutes randomized delay.
- NAS target: `/mnt/nas-backup/Fitness` on `//192.168.1.38/server-backup`.
- Retention: 14 daily and 8 weekly restore points; media blobs are content-addressed and deduplicated.

## Secret handling

The owner explicitly authorized installing the original MaxPlus keys on 2026-09-16. They are stored only in the server's mode-0600 runtime environment file and are not present in this repository. Runtime application/database secrets, VAPID keys, and initial account credentials remain in mode-0600 files under a mode-0700 directory.
