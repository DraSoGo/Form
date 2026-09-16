# Deployment

## Layout and service boundary

Production checkout: `/srv/docker/apps/fitness`. Compose project `fitness` contains web (Gunicorn), worker (`runworker`), and its own PostgreSQL 16. Database named volume `fitness_pgdata` stays local. Media bind: `/srv/docker/apps/fitness/data/media` to `/app/media`, owned by UID/GID 1000. Only web publishes `127.0.0.1:8095`; the internal database network has no published port. Outbound network allows configured AI/push HTTPS calls. Images run application code as UID 1000 with read-only root filesystems and a bounded temporary directory; logs and CPU/memory/process counts are limited.

Target HTTPS is `https://hp800-g5.tail985cfd.ts.net:8443`, through the existing Tailscale instance. Preserve existing Nextcloud `:443` and OJ routes. Take a timestamped copy of existing Tailscale Serve/Funnel JSON before changing only the new listener. The actual rollout/public reachability result belongs in final verification, not assumed here.

## First startup

Prepare the checkout and secret directory with root-owned restricted permissions. Copy `.env.example` to `secrets/runtime.env`, replace both placeholders with independently generated random values, and chmod the file 600 and secret directory 700. Use a secret editor or Python writing directly to the file; never put production secrets into shell command arguments, source, or terminal output. Set `DEBUG=false`, correct HTTPS origin/host and `SECURE_COOKIES=true`. Docker env injection is server-side; Docker administrators can read it. The initial deployment shares this file with all three containers, so protect Docker access as root-equivalent.

```sh
cd /srv/docker/apps/fitness
sudo install -d -m 700 secrets
sudo install -d -o 1000 -g 1000 -m 700 data/media
sudo docker compose build
sudo docker compose up -d db
sudo docker compose run --rm web python manage.py migrate --noinput
sudo docker compose run --rm web python manage.py createsuperuser
sudo docker compose up -d web worker
sudo docker compose ps
curl --fail http://127.0.0.1:8095/health
```

`createsuperuser` prompts securely for the account password; there is no password in source and no public registration. Use the application password-change page subsequently. If the app enforces single-user creation through a dedicated management command, use the command documented by core in the README. Account and provider secrets are required separately; manual tracking remains usable without AI keys.

Secure cookies require HTTPS for browser login. The loopback health endpoint is suitable for host monitoring; do not disable secure cookies for production testing. Proxy forwards HTTPS scheme, and Django only trusts that header because the service is reachable through loopback on the host. No public database or unauthenticated media location exists.

## Update

1. Check `git status`, current commit, image IDs and `docker compose ps`; preserve the last known-good image tag.
2. Run `sudo python3 ops/backup.py backup` and verify success. Ensure no migrations race with this backup.
3. Pull the reviewed revision. Set a unique `FITNESS_IMAGE_TAG` (for example the Git commit) when building and running Compose. The variable is Compose process environment, not runtime.env. Use the same value on all commands (`sudo` may discard caller environment).
4. Build, run migrations once, then recreate web and worker. Keep the database volume/media path unchanged.
5. Verify health, login, representative pages, scheduler logs and existing services. Run `restore-test` after schema changes. Record deployed revision/image tag and results.

No automatic startup migration is embedded in the image. Review migrations before execution. Rollback without schema changes uses the preserved image tag. For schema-incompatible rollback, follow the isolated data recovery process in [backup-restore.md](backup-restore.md); preserve live storage until acceptance.

## Monitoring

`/health` is unauthenticated, intentionally minimal and checked by the container. Add the public HTTPS health URL to existing Uptime Kuma if authorized. `docker compose logs --tail=100 web worker db` provides app/worker/DB logs. Backup status is in `data/backup-status.json` and systemd journals. Provider keys never belong in health output. Review worker logs for scheduler activity; a running process alone does not prove a successful daily summary.
