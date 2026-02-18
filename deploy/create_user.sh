#!/bin/bash
# Create a ZLM admin user in the running zlm-app container.
# Usage: ./deploy/create_user.sh <username> <password>

set -euo pipefail

USERNAME="${1:-}"
PASSWORD="${2:-}"

if [ -z "$USERNAME" ] || [ -z "$PASSWORD" ]; then
    echo "Usage: $0 <username> <password>"
    exit 1
fi

cat > /tmp/zlm_create_user.py << 'EOF'
import sys, os
sys.path.insert(0, "/app")

username = sys.argv[1]
password = sys.argv[2]

if len(password) < 8:
    print("Error: Password must be at least 8 characters.", file=sys.stderr)
    sys.exit(1)

from database import SessionLocal
from models.user import User

db = SessionLocal()
try:
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        print(f"Error: User \"{username}\" already exists.", file=sys.stderr)
        sys.exit(1)
    user = User(username=username)
    user.set_password(password)
    db.add(user)
    db.commit()
    print(f"User \"{username}\" created successfully.")
finally:
    db.close()
EOF

podman cp /tmp/zlm_create_user.py zlm-app:/tmp/zlm_create_user.py
podman exec zlm-app python /tmp/zlm_create_user.py "$USERNAME" "$PASSWORD"
rm -f /tmp/zlm_create_user.py
