# Fitness — personal training and nutrition coach

Single-user Django application for body measurements, food logs and photographs, workout plans and sessions, sleep/cardio, and AI coaching. Personal data stays in your PostgreSQL database; selected context is sent to the configured AI provider when an analysis is requested. AI changes require explicit acceptance.

## Documentation

- [Requirements](docs/requirements.md)
- [Infrastructure audit](docs/infrastructure-audit.md)
- [Architecture](docs/architecture.md)
- [Implementation plan](docs/implementation-plan.md)
- [Verification evidence](docs/verification.md)
- [Deployment and updates](docs/deployment.md)
- [Backup and restore](docs/backup-restore.md)
- [AI routing and configuration](docs/ai-routing.md)
- [Security](docs/security.md)

## Ownership and storage

Source workspace: `/home/drasogun/DraSoGun/Work/Server/fitness`.
Server deployment: `/srv/docker/apps/fitness` on `drasogo@192.168.1.48`.
Secrets: `secrets/runtime.env` and initial login `secrets/initial-login.txt`, restricted to the server account. Do not commit or publish these files.
Database is local PostgreSQL. NAS backup area is `/mnt/nas-backup/Fitness`; other applications' directories are outside this application's ownership.

No public registration, social login, email reset, or offline synchronization. The app is a coaching and record-keeping tool, not a diagnosis tool. Image estimates and smart-scale measurements are uncertain; use trends and correct food estimates when needed.

Current deployment and test status is recorded in [verification.md](docs/verification.md). Planned URLs are not claims of a running or verified service.
