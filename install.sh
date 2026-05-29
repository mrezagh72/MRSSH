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
WEB_BIND="${MRSSH_WEB_BIND:-0.0.0.0:8080}"
DOMAIN="${DOMAIN:-}"
EMAIL="${EMAIL:-admin@example.com}"

echo "[1/8] Installing packages..."
apt-get update
apt-get install -y \
  ca-certificates curl gnupg git nginx certbot python3-certbot-nginx \
  python3 python3-requests python3-pip sqlite3 openssh-server fail2ban openssl rsync ufw

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
MRSSH_WEB_BIND=0.0.0.0:8080
EOF

cp "$APP_DIR/.env" "$AGENT_DIR/.env"

echo "[6/8] Installing agent..."
cp "$APP_DIR/installer/agent/"*.py "$AGENT_DIR/"
cp "$APP_DIR/installer/bin/mrssh-backup" /usr/local/bin/mrssh-backup
chmod +x /usr/local/bin/mrssh-backup

python3 "$AGENT_DIR/db_migrate.py"

ADMIN_USER="$ADMIN_USER" ADMIN_PASS="$ADMIN_PASS" python3 - <<'PYADMIN'
import os, sqlite3, hashlib, secrets, time

DB="/opt/mrssh-agent/mrssh.db"
username=os.environ.get("ADMIN_USER","admin")
password=os.environ.get("ADMIN_PASS","")

salt=secrets.token_hex(16)
h=hashlib.sha256((salt+password).encode()).hexdigest()

con=sqlite3.connect(DB)
con.execute("""CREATE TABLE IF NOT EXISTS admin_auth (
username TEXT PRIMARY KEY,
password_hash TEXT NOT NULL,
salt TEXT NOT NULL,
updated_at INTEGER NOT NULL
)""")
con.execute("""INSERT INTO admin_auth(username,password_hash,salt,updated_at)
VALUES(?,?,?,?)
ON CONFLICT(username) DO UPDATE SET
password_hash=excluded.password_hash,
salt=excluded.salt,
updated_at=excluded.updated_at
""",(username,h,salt,int(time.time())))
con.commit()
con.close()
print("Admin auth initialized:", username)
PYADMIN

cp "$APP_DIR/installer/systemd/"mrssh*.service /etc/systemd/system/
cp "$APP_DIR/installer/systemd/"mrssh*.timer /etc/systemd/system/ 2>/dev/null || true

systemctl daemon-reload
systemctl enable --now mrssh-agent mrssh-traffic mrssh-limiter mrssh-expire mrssh-enforce
systemctl enable --now fail2ban || true
systemctl restart fail2ban || true
ufw allow 22/tcp || true
ufw allow 80/tcp || true
ufw allow 443/tcp || true
ufw allow 8080/tcp || true
ufw --force enable || true
systemctl enable --now mrssh-backup.timer || true

echo "[7/8] Starting backend..."
cd "$APP_DIR"
docker compose build
docker compose up -d

echo "[7/8] Building frontend static..."
docker build -t mrssh-frontend-static ./frontend
rm -rf /var/www/mrssh
mkdir -p /var/www/mrssh
docker create --name mrssh-front-tmp mrssh-frontend-static >/dev/null
docker cp mrssh-front-tmp:/usr/share/nginx/html/. /var/www/mrssh/
docker rm mrssh-front-tmp >/dev/null

echo "[7/8] Configuring Nginx..."
if [ -n "$DOMAIN" ]; then
  SERVER_NAME="$DOMAIN"
else
  SERVER_NAME="_"
fi

cat > /etc/nginx/sites-available/mrssh <<EOF
server {
    listen 8080;
    server_name $SERVER_NAME;

    root /var/www/mrssh;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_http_version 1.1;
        proxy_connect_timeout 3s;
        proxy_read_timeout 30s;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location / {
        try_files \$uri /index.html;
    }
}
EOF

ln -sf /etc/nginx/sites-available/mrssh /etc/nginx/sites-enabled/mrssh
nginx -t
systemctl restart nginx

echo "[CHECK] Agent..."
sleep 2
curl -fsS -H "X-Secret: $(grep '^MRSSH_SECRET=' /opt/mrssh/.env | cut -d= -f2-)" http://127.0.0.1:9911/dashboard >/dev/null || { echo "Agent health check failed"; exit 1; }

echo "[CHECK] Backend..."
sleep 5
curl -fsS http://127.0.0.1:8000/health >/dev/null || { echo "Backend health check failed"; exit 1; }

echo "[CHECK] Frontend..."
test -f /var/www/mrssh/index.html || { echo "Frontend index missing"; exit 1; }
grep -q 'id="root"' /var/www/mrssh/index.html || { echo "Frontend index invalid"; exit 1; }

echo "[CHECK] Nginx..."
curl -fsS http://127.0.0.1:8080/api/health >/dev/null || { echo "Nginx/API health check failed"; exit 1; }

if [ -n "$DOMAIN" ]; then
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" || true
fi

echo "[8/8] Done"
echo ""
echo "MRSSH installed"
SERVER_IP=$(curl -4 -s https://api.ipify.org || hostname -I | awk '{print $1}')
if [ -n "$DOMAIN" ]; then
  echo "Panel URL: https://$DOMAIN"
else
  echo "Panel URL: http://$SERVER_IP:8080"
fi
echo "Username: $ADMIN_USER"
echo "Password: $ADMIN_PASS"
echo ""
echo "For domain + SSL, configure Nginx and Certbot after install."
