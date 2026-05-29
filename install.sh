#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/mrssh"
AGENT_DIR="/opt/mrssh-agent"
BACKUP_DIR="/opt/mrssh-backups"

echo "=== MRSSH Installer ==="

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root"
  exit 1
fi

ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-$(openssl rand -base64 12)}"
MRSSH_SECRET="${MRSSH_SECRET:-$(openssl rand -hex 32)}"
WEB_BIND="${MRSSH_WEB_BIND:-127.0.0.1:8080}"
DOMAIN="${DOMAIN:-}"
EMAIL="${EMAIL:-admin@example.com}"

echo "[1/8] Installing packages..."
apt-get update
apt-get install -y \
  ca-certificates curl gnupg git nginx certbot python3-certbot-nginx \
  python3 python3-requests python3-pip sqlite3 openssh-server fail2ban openssl rsync

if ! command -v docker >/dev/null 2>&1; then
  echo "[2/8] Installing Docker..."
  curl -fsSL https://get.docker.com | sh
else
  echo "[2/8] Docker already installed"
fi

echo "[3/8] Preparing directories..."
mkdir -p "$APP_DIR" "$AGENT_DIR" "$BACKUP_DIR"

echo "[4/8] Copying project..."
rsync -a --delete \
  --exclude ".git" \
  --exclude "node_modules" \
  --exclude "dist" \
  ./ "$APP_DIR/"

echo "[5/8] Creating env..."
cat > "$APP_DIR/.env" <<EOF
SECRET_KEY=$(openssl rand -hex 32)
ADMIN_USERNAME=$ADMIN_USER
ADMIN_PASSWORD=$ADMIN_PASS
MRSSH_SECRET=$MRSSH_SECRET
MRSSH_WEB_BIND=$WEB_BIND
EOF

cp "$APP_DIR/.env" "$AGENT_DIR/.env"

echo "[6/8] Installing agent..."
cp "$APP_DIR/installer/agent/"*.py "$AGENT_DIR/"
cp "$APP_DIR/installer/bin/mrssh-backup" /usr/local/bin/mrssh-backup
chmod +x /usr/local/bin/mrssh-backup

python3 "$AGENT_DIR/db_migrate.py"

cp "$APP_DIR/installer/systemd/"mrssh*.service /etc/systemd/system/
cp "$APP_DIR/installer/systemd/"mrssh*.timer /etc/systemd/system/ 2>/dev/null || true

systemctl daemon-reload
systemctl enable --now mrssh-agent mrssh-traffic mrssh-limiter mrssh-expire mrssh-enforce
systemctl enable --now mrssh-backup.timer || true

echo "[7/8] Starting panel..."
cd "$APP_DIR"
if [ -n "$DOMAIN" ]; then
  echo "[SSL] Configuring Nginx for $DOMAIN..."
  cat > /etc/nginx/sites-available/mrssh <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
  ln -sf /etc/nginx/sites-available/mrssh /etc/nginx/sites-enabled/mrssh
  nginx -t
  systemctl reload nginx
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" || true
fi

docker compose build
docker compose up -d

echo "[8/8] Done"
echo ""
echo "MRSSH installed"
echo "Panel local: http://127.0.0.1:8080"
echo "Username: $ADMIN_USER"
echo "Password: $ADMIN_PASS"
echo ""
echo "For domain + SSL, configure Nginx and Certbot after install."
