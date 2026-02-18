# Zimbra Lifecycle Manager — Container Deployment Guide

Podman Compose deployment on Rocky Linux 9.7 with MariaDB 10.11.

## Prerequisites

- Rocky Linux 9.7 (or RHEL 9 compatible)
- Podman 6.5+ and podman-compose
- Ports: 8000 (app), 3306 (db, internal only)

```bash
dnf install -y podman podman-compose
```

## 1. Create Podman Secrets

All sensitive values are stored as podman secrets — never in config files or environment variables.

```bash
# Database password
printf 'YOUR_DB_PASSWORD' | podman secret create zlm_db_password -

# Application secret key (generate a random one)
python3 -c "import secrets; print(secrets.token_urlsafe(64))" | podman secret create zlm_secret_key -

# Zimbra admin password
printf 'YOUR_ZIMBRA_ADMIN_PASSWORD' | podman secret create zlm_zimbra_password -

# Encryption key (generate or copy existing)
# Option A: Generate new key
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" | podman secret create zlm_encryption_key -

# Option B: Use existing key from bare-metal install
cat /path/to/existing/conf/encryption.key | podman secret create zlm_encryption_key -
```

Verify secrets exist:
```bash
podman secret ls
```

## 2. Prepare Configuration

```bash
cd /path/to/zimbra-lifecycle-fastapi

# Copy and edit the environment file
cp .env.example .env
# Edit .env — adjust worker count, log level, etc.

# Copy and edit config (only non-secret values needed)
cp conf/app.conf.example conf/app.conf
# Edit conf/app.conf — set zimbra admin_url, admin_user, etc.
# Passwords can be left blank; they will be read from secrets.

# Create data directories and set ownership to the container's zlm user (uid 999)
mkdir -p data/{uploads,exports,logs}
# Rootless Podman (recommended):
podman unshare chown -R 999:999 data/
# Root Podman:
# chown -R 999:999 data/
```

## 3. Build the Container Image

```bash
podman-compose build
```

## 4. Start Services

```bash
podman-compose up -d
```

Check that both containers are healthy:
```bash
podman-compose ps
podman ps
```

The app will be available at `http://<host>:8000`.

Test the health endpoint:
```bash
curl http://localhost:8000/healthz
```

## 5. Initial Sync (Populate Accounts from Zimbra)

Use the **Settings** page (`/settings/`) → **Sync Now** button, or run via CLI:

```bash
podman-compose exec app python -m cli.main sync
```

## 6. Create Admin User

```bash
bash deploy/create_user.sh admin 'YourSecurePassword'
```

> Always use single quotes around the password to prevent the shell from interpreting
> special characters such as `!`. The script passes credentials via environment
> variables so they are never visible in process listings or shell history.

## Maintenance

### View Logs

```bash
# Application logs
podman-compose logs -f app

# Database logs
podman-compose logs -f db

# Follow both
podman-compose logs -f
```

### Backup Database

```bash
podman-compose exec db mariadb-dump -u zlm -p zimbra_lifecycle | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz
```

### Restore Database

```bash
gunzip -c backup_YYYYMMDD_HHMMSS.sql.gz | podman-compose exec -T db mariadb -u zlm -p zimbra_lifecycle
```

### Upgrade

```bash
cd /path/to/zimbra-lifecycle-fastapi
git pull

# Rebuild and restart
podman-compose build
podman-compose up -d
```

Alembic migrations run automatically on startup via the entrypoint script.

### Stop Services

```bash
podman-compose down
```

To also remove the database volume (destroys data):
```bash
podman-compose down -v
```

### Sync Scheduling

Sync scheduling is managed in-app via **Settings → Auto-Sync Schedule** (`/settings/`).
Choose Off / 1 h / 2 h / 4 h / 8 h / 12 h / 24 h — the schedule persists in the
database and is restored automatically when the container restarts. No cron job needed.

To confirm the scheduler started after deployment:
```bash
podman-compose logs app | grep -i scheduler
```

### Purge Queue Cron (optional)

The purge queue is not yet triggered automatically. Add to root's crontab if desired:
```bash
# Process purge queue daily at 2am
0 2 * * * podman-compose -f /path/to/zimbra-lifecycle-fastapi/podman-compose.yml exec -T app python -m cli.main purge >> /var/log/zlm-purge.log 2>&1
```

## Reverse Proxy (Optional)

Place nginx in front for TLS termination:

```nginx
server {
    listen 443 ssl;
    server_name zlm.example.com;

    ssl_certificate     /etc/pki/tls/certs/zlm.crt;
    ssl_certificate_key /etc/pki/tls/private/zlm.key;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `503` on `/healthz` | Check db is healthy: `podman-compose ps` |
| Container exits immediately | Check logs: `podman-compose logs app` |
| "Encryption key not found" | Verify `zlm_encryption_key` secret: `podman secret ls` |
| DB connection refused | Ensure `db` service started first and is healthy |
| Permission denied on volumes | Verify `:Z` SELinux labels are in compose file |
| Login fails after `create-user` | Shell may have mangled the password (e.g. `!` triggers history expansion). Reset it — see below. |

### Reset a User Password

Generate a fresh bcrypt hash inside the container and write it directly to the database:

```bash
# 1. Generate hash (replace 'NewPassword' with your chosen password)
NEW_HASH=$(podman exec zlm-app python3 -c \
  "from passlib.hash import bcrypt; print(bcrypt.hash('NewPassword'))")

# 2. Write it to the DB
podman exec zlm-db mariadb -u zlm -p"$(cat /run/secrets/zlm_db_password)" \
  zimbra_lifecycle \
  -e "UPDATE users SET password_hash='$NEW_HASH' WHERE username='admin';"
```
