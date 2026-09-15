# Security and privacy

Single-user Django server sessions use Argon2 password hashing, CSRF protection, HttpOnly secure cookies, SameSite=Lax and session expiration. No public signup or client-side provider credentials are intended. Login throttling and photo validation are enforced by the application; see tests and final verification for measured outcomes. Change the account password through the authenticated page. Use an interactive management command only for administrator recovery.

Only loopback web port 8095 is published; access uses a dedicated HTTPS proxy listener. PostgreSQL is separate from all existing app databases on an internal Compose network. App containers run as UID1000, drop capabilities, disallow privilege escalation and use a read-only image. Resource/log limits protect the small server. These controls do not protect against a host/Docker administrator.

Keep `/srv/docker/apps/fitness/secrets/runtime.env` at mode 600 in a mode-700 directory. Secrets are injected at runtime, omitted from Git/build contexts/backups and never displayed in frontend settings. Treat previously exposed provider keys as compromised and replace them. Store a separate protected recovery copy of Django, database and VAPID secrets. Changing VAPID keys requires subscription renewal. Rotating database credentials also requires changing the actual PostgreSQL role password; changing the environment alone does not modify an initialized database.

Photos are private authenticated resources stored outside the database. Retention removes files while preserving nutrition metadata. NAS backups contain private health records and can retain deleted photos through their historical snapshots; read [backup-restore.md](backup-restore.md). NAS access controls protect archive confidentiality; backups are not application-encrypted at rest. Database archives include sessions, so invalidate restored sessions before reopening an old backup publicly when appropriate.

AI receives only the selected bounded context and explicit photo analysis requests. Provider/model capabilities must be confirmed; no exposed keys are reused. Application suggestions require explicit Accept to change active targets/plans. Push notifications should contain generic text, not health details on lock screens.

Do not expose `/app/media` with a reverse-proxy static alias, enable Django DEBUG publicly, publish DB ports, or add secrets to example files. Keep Django/Python/PostgreSQL dependencies updated through tested builds and preserve a rollback image before upgrade.
