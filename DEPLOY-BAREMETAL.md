# Zimbra Lifecycle Manager — Bare-Metal / Incus Container Deployment

Direct installation on Rocky Linux 9.x without Podman or Docker.
Suitable for bare-metal servers and Incus system containers.

## Prerequisites

- Rocky Linux 9.x (fresh install or Incus system container)
- Root or sudo access
- Network access to your Zimbra server

---

## 1. Install System Packages

```bash
sudo dnf install -y python3 python3-pip git mariadb-server
```

---

## 2. Configure MariaDB

Enable and start the service, then run the secure-installation wizard:

```bash
sudo systemctl enable --now mariadb
sudo mariadb-secure-installation
```

Recommended answers: set a root password, remove anonymous users, disallow remote root login, remove test database, reload privileges.

---

## 3. Create the Database and User

```bash
sudo mariadb -u root -p << 'EOF'
CREATE DATABASE IF NOT EXISTS zimbra_lifecycle
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'zlm'@'localhost' IDENTIFIED BY 'YOUR_DB_PASSWORD';
GRANT ALL PRIVILEGES ON zimbra_lifecycle.* TO 'zlm'@'localhost';
FLUSH PRIVILEGES;
EOF
```

Replace `YOUR_DB_PASSWORD` with a strong password. Keep it handy — you'll put it in `app.conf` in a later step.

---

## 4. Create Application User and Clone Repo

Run the application as a dedicated system user with no login shell:

```bash
sudo useradd -r -m -d /opt/ZLM -s /sbin/nologin zlm
sudo git clone https://github.com/farmer1776/ZLM.git /opt/ZLM
sudo chown -R zlm:zlm /opt/ZLM
```

---

## 5. Set Up Python Virtual Environment

```bash
sudo -u zlm python3 -m venv /opt/ZLM/venv
sudo -u zlm /opt/ZLM/venv/bin/pip install --upgrade pip
sudo -u zlm /opt/ZLM/venv/bin/pip install -r /opt/ZLM/requirements.txt
```

---

## 6. Generate the Encryption Key

The app uses a Fernet key to encrypt sensitive values in `app.conf`. Generate it once:

```bash
cd /opt/ZLM && sudo -u zlm venv/bin/python -m cli.main generate-key
```

This writes the key to `conf/encryption.key`.

> **Back this file up.** Losing it means you cannot decrypt your stored passwords and will need to re-encrypt everything.

---

## 7. Configure the Application

```bash
sudo -u zlm cp /opt/ZLM/conf/app.conf.example /opt/ZLM/conf/app.conf
sudo -u zlm nano /opt/ZLM/conf/app.conf
```

Fill in all values in plaintext — they will be encrypted in the next step:

```ini
[django]
secret_key    = <paste a long random string here>
debug         = false
allowed_hosts = localhost,127.0.0.1,<server-ip-or-hostname>

[zimbra]
admin_url      = https://your-zimbra-server:7071/service/admin/soap
admin_user     = admin@example.com
admin_password = <zimbra admin password>

[database]
host     = localhost
port     = 3306
name     = zimbra_lifecycle
user     = zlm
password = <the DB password you set in step 3>
```

To generate a suitable `secret_key`:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

### Encrypt sensitive values

Once `app.conf` is saved with plaintext values, encrypt them in place:

```bash
cd /opt/ZLM && sudo -u zlm venv/bin/python -m cli.main encrypt-config
```

The `secret_key`, `admin_password`, and `password` fields will be replaced with Fernet-encrypted ciphertext. The file is safe to read as root after this step.

---

## 8. Create Data Directories

```bash
sudo -u zlm mkdir -p /opt/ZLM/data/{uploads,exports,logs}
```

---

## 9. Run Database Migrations

```bash
cd /opt/ZLM && sudo -u zlm venv/bin/alembic upgrade head
```

---

## 10. Create Admin User

```bash
cd /opt/ZLM && sudo -u zlm venv/bin/python -m cli.main create-user admin
```

You will be prompted for a password twice. Use a strong password and avoid `!` — if you must use special characters, run the command inside `sudo -u zlm bash` to control the shell environment.

---

## 11. Create the systemd Service

```bash
sudo tee /etc/systemd/system/zlm.service << 'EOF'
[Unit]
Description=Zimbra Lifecycle Manager
After=network.target mariadb.service
Requires=mariadb.service

[Service]
Type=exec
User=zlm
Group=zlm
WorkingDirectory=/opt/ZLM
ExecStart=/opt/ZLM/venv/bin/gunicorn main:app -c /opt/ZLM/deploy/gunicorn.conf.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now zlm
```

Verify it started:

```bash
sudo systemctl status zlm
curl http://localhost:8000/healthz
# {"status":"ok"}
```

---

## 12. (Optional) Firewall

If you want the app accessible from other hosts:

```bash
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

---

## 13. (Optional) Reverse Proxy with nginx

Install nginx and configure it to terminate TLS and proxy to Gunicorn:

```bash
sudo dnf install -y nginx
```

Create `/etc/nginx/conf.d/zlm.conf`:

```nginx
server {
    listen 80;
    server_name zlm.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name zlm.example.com;

    ssl_certificate     /etc/pki/tls/certs/zlm.crt;
    ssl_certificate_key /etc/pki/tls/private/zlm.key;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo systemctl enable --now nginx
```

Update `allowed_hosts` in `conf/app.conf` to include your domain, then re-encrypt and restart:

```bash
# Edit app.conf (set allowed_hosts), then:
cd /opt/ZLM && sudo -u zlm venv/bin/python -m cli.main encrypt-config
sudo systemctl restart zlm
```

---

## Maintenance

### View Logs

```bash
sudo journalctl -u zlm -f
```

### Upgrade

```bash
cd /opt/ZLM
sudo -u zlm git pull
sudo -u zlm venv/bin/pip install -r requirements.txt
sudo -u zlm venv/bin/alembic upgrade head
sudo systemctl restart zlm
```

### Backup Database

```bash
mariadb-dump -u zlm -p zimbra_lifecycle | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz
```

### Restore Database

```bash
gunzip -c backup_YYYYMMDD_HHMMSS.sql.gz | mariadb -u zlm -p zimbra_lifecycle
```

### Reset a User Password

```bash
cd /opt/ZLM
sudo -u zlm venv/bin/python -c "
from database import SessionLocal
from models.user import User
db = SessionLocal()
u = db.query(User).filter(User.username == 'admin').first()
u.set_password('NewPassword')
db.commit()
print('Password updated.')
"
```

### Purge Queue Cron (Optional)

```bash
crontab -e -u zlm
```

```cron
# Process purge queue daily at 2am
0 2 * * * cd /opt/ZLM && venv/bin/python -m cli.main purge >> data/logs/purge.log 2>&1
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `systemctl status zlm` shows failed | Check logs: `journalctl -u zlm -n 50` |
| `{"status":"error"}` on `/healthz` | MariaDB not running or wrong credentials in `app.conf` |
| "Encryption key not found" | Verify `conf/encryption.key` exists and is owned by `zlm` |
| App starts but can't read config | Check `conf/app.conf` permissions: `sudo chown zlm:zlm conf/app.conf` |
| Login fails | Reset password using the Python snippet in the Maintenance section above |
| `alembic upgrade head` fails | Confirm DB user has `ALL PRIVILEGES` on the `zimbra_lifecycle` database |
