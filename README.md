# Zimbra Lifecycle Manager (ZLM)

A web-based management tool for Zimbra mailbox lifecycle operations — account syncing, status changes, bulk operations, audit logging, and scheduled purging.

## Application Stack

| Layer | Technology |
|---|---|
| **Runtime** | Python 3.9 |
| **Web Framework** | FastAPI + Uvicorn |
| **WSGI Server** | Gunicorn (UvicornWorker) |
| **Database** | MariaDB 10.11 (utf8mb4) |
| **ORM** | SQLAlchemy 2.0 |
| **Migrations** | Alembic |
| **Templates** | Jinja2 |
| **Auth** | Session-based (bcrypt + Fernet-encrypted config) |
| **Container Runtime** | Podman 6.5 + podman-compose |
| **Host OS** | Rocky Linux 9.7 |

## Project Structure

```
├── main.py                  # FastAPI application entry point
├── config.py                # Settings (secrets → env → app.conf)
├── database.py              # SQLAlchemy engine + session
├── dependencies.py          # Dependency injection helpers
├── template_filters.py      # Jinja2 custom filters
├── alembic/                 # Database migrations
├── apps/zimbra_client/      # Zimbra SOAP API client
├── cli/                     # CLI tools (sync, purge, user mgmt, key gen)
├── conf/                    # app.conf + encryption.key (not committed)
├── core/                    # Encryption utilities
├── data/                    # Runtime data — logs, uploads, exports (not committed)
├── deploy/                  # Deployment configs
│   ├── entrypoint.sh        # Container entrypoint (wait-for-db → migrate → serve)
│   ├── gunicorn.conf.py     # Gunicorn settings
│   └── mariadb-init.sql     # DB init script
├── middleware/               # Security headers, rate limiting, audit context
├── models/                  # SQLAlchemy models
├── routers/                 # FastAPI route handlers
├── services/                # Business logic (sync, bulk ops, accounts)
├── static/                  # CSS + JS assets
├── templates/               # Jinja2 HTML templates
├── Containerfile            # Multi-stage container build
├── podman-compose.yml       # Compose file (app + db)
├── .env.example             # Environment variable reference
└── DEPLOY.md                # Detailed deployment & maintenance guide
```

## Provisioning on Rocky Linux 9.7

These steps assume a fresh Rocky Linux 9.7 server with Podman 6.5 already installed.

### 1. Install podman-compose and runc

```bash
dnf install -y podman-compose runc git
```

### 2. Proxmox / Incus VMs — cgroup workaround

> **Skip this step on bare-metal hosts.** Proxmox VMs (and Incus containers) restrict
> cgroup controller delegation, which prevents the default `crun` runtime from starting
> containers. Apply this config to use `runc` with the cgroupfs manager instead:

```bash
mkdir -p /etc/containers
cat > /etc/containers/containers.conf << 'EOF'
[containers]
default_sysctls = []

[engine]
runtime = "runc"
cgroup_manager = "cgroupfs"
EOF
```

### 3. Clone the repository

```bash
cd /opt
git clone https://github.com/farmer1776/ZLM.git
cd ZLM
```

### 4. Create podman secrets

All sensitive credentials are stored as podman secrets — never in files or environment variables.

```bash
# Database password
printf 'YOUR_SECURE_DB_PASSWORD' | podman secret create zlm_db_password -

# Application session secret key
python3 -c "import secrets; print(secrets.token_urlsafe(64))" | podman secret create zlm_secret_key -

# Zimbra admin password
printf 'YOUR_ZIMBRA_ADMIN_PASSWORD' | podman secret create zlm_zimbra_password -

# Fernet encryption key for config values
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" | podman secret create zlm_encryption_key -
```

> **Migrating from an existing install?** Use your existing encryption key instead:
> ```bash
> cat /path/to/old/conf/encryption.key | podman secret create zlm_encryption_key -
> ```

Verify all four secrets exist:
```bash
podman secret ls
```

### 5. Configure the application

```bash
# Environment variables (non-secret settings)
cp .env.example .env
# Edit .env — adjust GUNICORN_WORKERS, log level, etc.

# Application config (Zimbra connection details)
cp conf/app.conf.example conf/app.conf
# Edit conf/app.conf:
#   - Set zimbra admin_url to your Zimbra server
#   - Set zimbra admin_user
#   - Leave passwords blank (read from secrets)
```

### 6. Create data directories

```bash
mkdir -p data/{uploads,exports,logs}
chown -R 999:999 data/
```

### 7. Build the container image

```bash
podman-compose build
```

### 8. Start services

```bash
podman-compose up -d
```

This starts:
- **zlm-db** — MariaDB 10.11 with a health check
- **zlm-app** — waits for DB health → runs Alembic migrations → starts Gunicorn

Check status:
```bash
podman-compose ps
```

Verify the health endpoint:
```bash
curl http://localhost:8000/healthz
# {"status":"ok"}
```

### 9. Sync accounts from Zimbra

```bash
podman-compose exec app python -m cli.main sync
```

### 10. Create an admin user

```bash
sudo bash deploy/create_user.sh admin 'YourPassword123!'
```

### 11. (Optional) Set up cron jobs

```bash
crontab -e
```

```cron
# Sync accounts every 4 hours
0 */4 * * * podman-compose -f /opt/ZLM/podman-compose.yml exec -T app python -m cli.main sync >> /var/log/zlm-sync.log 2>&1

# Process purge queue daily at 2am
0 2 * * * podman-compose -f /opt/ZLM/podman-compose.yml exec -T app python -m cli.main purge >> /var/log/zlm-purge.log 2>&1
```

### 12. (Optional) Firewall

```bash
firewall-cmd --permanent --add-port=8000/tcp
firewall-cmd --reload
```

Or if placing behind nginx for TLS, open 443 instead and see the reverse proxy section in [DEPLOY.md](DEPLOY.md).

## Upgrading

```bash
cd /opt/ZLM
git pull
podman-compose build
podman-compose up -d
```

Migrations run automatically on container start.

## Logs

```bash
podman-compose logs -f app    # application logs
podman-compose logs -f db     # database logs
podman-compose logs -f        # both
```

## Further Reading

See [DEPLOY.md](DEPLOY.md) for backup/restore procedures, troubleshooting, and reverse proxy configuration.
