# Documentation guide

Use this index to find the document that matches the work you are doing. All hostnames, usernames, and network addresses use placeholders so the repository can be shared without exposing a private network.

## Product and design

| Document | Purpose |
|---|---|
| [Requirements](requirements.md) | Original product scope, constraints, and acceptance criteria |
| [Architecture](architecture.md) | Runtime components, application boundaries, and data flow |
| [Core contracts](core-contracts.md) | Domain rules shared by core and coaching code |
| [Implementation plan](implementation-plan.md) | Build order and verification strategy |

## Operations

| Document | Purpose |
|---|---|
| [Deployment](deployment.md) | Install, update, monitor, and roll back the application |
| [Backup and restore](backup-restore.md) | Create, verify, retain, and test NAS recovery points |
| [NAS actions](NAS-ACTIONS.md) | Storage ownership and NAS-side requirements |
| [Security and privacy](security.md) | Authentication, secret storage, media privacy, and network exposure |
| [AI routing](ai-routing.md) | Configure providers, verify models, and understand fallback behavior |

## Evidence and history

| Document | Purpose |
|---|---|
| [Verification record](verification.md) | Automated and production verification results |
| [Infrastructure audit](infrastructure-audit.md) | Sanitized record of the host assessment used for the initial design |

## Placeholder reference

| Placeholder | Replace with |
|---|---|
| `<SSH_USER>` | Deployment account on the server |
| `<SERVER_IP>` | Private address or DNS name used on the trusted LAN |
| `<SERVER_HOST>` | Server hostname |
| `<NAS_IP>` | NAS address or resolvable hostname |
| `<PUBLIC_HOST>` | HTTPS hostname exposed through your proxy or private network |
| `<LOCAL_WORKSPACE>` | Local source checkout parent directory |
| `<EXISTING_APP_DOMAIN>` | Domain already used by another service on the host |
| `<CODEX_SESSION_ID>` | Optional local development-session reference |

Keep real credentials, addresses, provider keys, and recovery secrets in protected deployment configuration. Do not commit them to this repository.
