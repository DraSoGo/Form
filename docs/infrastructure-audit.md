# Infrastructure audit — 2026-09-15

Read-only SSH audit of <SSH_USER>@<SERVER_IP> before implementation. No existing service configuration changed.

## Host and resources
Ubuntu 24.04.4 LTS, <SERVER_HOST>, KVM guest, 2 vCPUs (i5-9500 exposed), 5.7 GiB RAM with 3.1 GiB available, 3.8 GiB swap (1.7 GiB used). Root ext4/LVM: 56 GiB, 17 GiB free. Virtual disk reports rotational; physical SSD backing is unverified. Docker 29.7.2, Compose v5.5.0. Use local PostgreSQL storage, limit app resources and logs. Avoid unnecessary build load on host.

## Existing services
Seven Compose projects under /srv/docker/apps: beszel, homepage, immich, nextcloud, OJ, paperless, uptime-kuma. All 21 containers initially running and healthy where checks exist. PostgreSQL 14/16/18 instances are application-owned, Redis/Valkey likewise. /srv/docker/postgres, redis and caddy exist but are empty. No shared database/reverse proxy available for reuse. OJ git branch deploy clean. Local Server workspace has existing docs/ops but no git repository; new project will live in fitness/ with its own Git repository.

Occupied TCP ports included 22, 53, 80, 443, 2283, 3000, 3001, 8000, 8080, 8081, and 8090 plus dynamic private-network listeners. Fitness reserves host port `8095`; the firewall must restrict it to trusted LAN or private-network clients. PostgreSQL has no host port.

## Access and firewall
Tailscale Funnel HTTPS <PUBLIC_HOST>:443 proxies / to http://<SERVER_IP>:8081 (Nextcloud). Preserve exactly. Proposed isolated additional Funnel listener :8443 for Fitness; check authorization and take config backup before adding. OJ uses nginx and Cloudflare tunnel for <EXISTING_APP_DOMAIN> and upload.<EXISTING_APP_DOMAIN>. Do not change either. UFW detailed rules unreadable without sudo; supplied password was rejected once. No credential guessing or privilege workaround attempted. Administrator credential clarification pending.

## Storage and backups
CIFS mounts: /mnt/nas-backup -> //<NAS_IP>/server-backup; /mnt/immich; /mnt/paperless/media and consume. /mnt/nextcloud is bound by Nextcloud but was not shown as a current CIFS mount: do not alter. NAS backup share has per-app folders, 1.7 TiB available, owner <SSH_USER> 0700 directories/0600 files. Dedicated /mnt/nas-backup/Fitness is appropriate. Do not touch sibling app folders or TrueNAS datasets. Live database and photos in dedicated local Docker volumes; NAS for database archives and incremental media backups. No TrueNAS dataset creation needed for backup-only use.

Existing backup systemd timers run daily with randomized delay, persistent scheduling, Uptime Kuma success/failure hooks. Beszel and Kuma monitor services, NAS exporter present. Existing Docker json-file logs have no per-container rotation configured; fitness will specify rotation. User crontab absent; application-specific user cron can provide backups without modifying system units.

## Architecture decision
Django 5.2 LTS with server-rendered responsive HTML, small JavaScript enhancements and a PWA service worker; dedicated PostgreSQL 16; Gunicorn web service and database-backed scheduler worker using same image. Django provides ORM/migrations, server sessions, CSRF, password change and Argon2 support, reducing custom security code and RAM versus separate SPA/API/Redis/Celery stacks. Add explicit database-backed login limiting, image decoding/re-encoding, structured Pydantic AI schemas, bounded provider adapters. No existing service dependencies. Alternatives: SPA/API doubles deployment surface; reusing another app's DB creates unnecessary coupling. Django security reference: https://docs.djangoproject.com/en/5.2/topics/security/ ; Funnel reference: https://tailscale.com/docs/features/tailscale-funnel .

## Open constraints
Rotated AI keys not located: never install keys marked exposed in the request into production. AI unavailable state must remain usable with manual entry. Sudo unavailable so full firewall inspection and Funnel setup may need user action. Physical storage backing unverified. Public deployment must pass secure session and regression checks before exposure.

## Audit addendum: privileged checks completed
The privileged follow-up confirmed that UFW was active with incoming deny, outgoing allow, and routed deny defaults. SSH and application ports were restricted to their intended LAN or private-network interfaces. The audit inspected firewall state without changing it.
