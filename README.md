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
| **Container Runtime** | Podman 5.x + podman-compose |
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

These steps assume a fresh Rocky Linux 9.7 server with Podman 5.x already installed. All commands run as a **non-root user** (rootless Podman).

### 1. Enable linger

Allows your containers to keep running after you log out:

```bash
sudo loginctl enable-linger $USER
```

### 2. Install podman-compose and runc

```bash
sudo dnf install -y podman-compose runc git
```

### 3. Proxmox / Incus VMs — cgroup and networking workaround

> **Skip this step on bare-metal hosts.** Proxmox VMs (and Incus containers) restrict
> cgroup controller delegation and don't auto-load the `ip_tables` kernel module, both
> of which prevent containers from starting.

Load `ip_tables` now and persist it across reboots:

```bash
sudo modprobe ip_tables
echo "ip_tables" | sudo tee /etc/modules-load.d/ip_tables.conf
```

Apply the cgroup config to use `runc` with the cgroupfs manager:

```bash
sudo mkdir -p /etc/containers
sudo tee /etc/containers/containers.conf << 'EOF'
[containers]
default_sysctls = []

[engine]
runtime = "runc"
cgroup_manager = "cgroupfs"
EOF
```

### 4. Clone the repository

```bash
sudo git clone https://github.com/farmer1776/ZLM.git /opt/ZLM
sudo chown -R $USER:$USER /opt/ZLM
cd /opt/ZLM
```

### 5. Create podman secrets

All sensitive credentials are stored as podman secrets — never in files or environment variables.

```bash
# Database password
printf 'YOUR_SECURE_DB_PASSWORD' | podman secret create zlm_db_password -

# Application session secret key
python3 -c "import secrets; print(secrets.token_urlsafe(64))" | podman secret create zlm_secret_key -

# Zimbra admin password
printf 'YOUR_ZIMBRA_ADMIN_PASSWORD' | podman secret create zlm_zimbra_password -

# Fernet encryption key for config values
python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())" | podman secret create zlm_encryption_key -
```

> **Migrating from an existing install?** Use your existing encryption key instead:
> ```bash
> cat /path/to/old/conf/encryption.key | podman secret create zlm_encryption_key -
> ```

Verify all four secrets exist:
```bash
podman secret ls
```

### 6. Configure the application

```bash
cp .env.example .env
cp conf/app.conf.example conf/app.conf
```

Edit `conf/app.conf` and set the following:

```ini
[zimbra]
admin_url = https://your-zimbra-server:7071/service/admin/soap
admin_user = admin@example.com
# admin_password is read from the zlm_zimbra_password secret — leave blank

[database]
host = db        # must be "db" to reach the database container
# password is read from the zlm_db_password secret — leave blank
```

### 7. Create data directories

The container runs as the non-root `zlm` user (uid 999). Use `podman unshare` to set ownership correctly inside the user namespace:

```bash
mkdir -p data/{uploads,exports,logs}
podman unshare chown -R 999:999 data/
```

> **Running as root?** Use `chown -R 999:999 data/` instead.

### 8. Build the container image

```bash
podman-compose build
```

### 9. Start services

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

### 10. Sync accounts from Zimbra

```bash
podman-compose exec app python -m cli.main sync
```

### 11. Create an admin user

```bash
bash deploy/create_user.sh admin 'YourSecurePassword1'
```

> **Tip:** Always use single quotes around the password argument to prevent the shell from interpreting special characters.

### 12. Enable autostart on reboot

Linger keeps containers alive through logouts, but a systemd user service is needed to restart them after a reboot.

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/zlm.service << 'EOF'
[Unit]
Description=Zimbra Lifecycle Manager (podman-compose)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/ZLM
ExecStartPre=/usr/bin/podman rm -af
ExecStart=/usr/bin/podman-compose up -d
ExecStop=/usr/bin/podman-compose down
TimeoutStartSec=120

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable zlm.service
```

### 13. (Optional) Firewall

```bash
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

Or if placing behind nginx for TLS, open 443 instead and see the reverse proxy section in [DEPLOY.md](DEPLOY.md).

### 14. (Optional) Set up cron jobs

Sync scheduling is now managed in-app via the **Settings** page (`/settings/`).
You can choose Off / 1h / 2h / 4h / 8h / 12h / 24h; the schedule persists in the
database and is restored automatically on container restart.

Only the purge queue still requires a cron job if you want it automated:

```bash
crontab -e
```

```cron
# Process purge queue daily at 2am
0 2 * * * podman-compose -f /opt/ZLM/podman-compose.yml exec -T app python -m cli.main purge >> /var/log/zlm-purge.log 2>&1
```

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
