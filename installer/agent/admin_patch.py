import sqlite3, hashlib, secrets, time

DB="/opt/mrssh-agent/mrssh.db"
con=sqlite3.connect(DB)
cur=con.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS admin_auth (
  username TEXT PRIMARY KEY,
  password_hash TEXT NOT NULL,
  salt TEXT NOT NULL,
  updated_at INTEGER NOT NULL
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
)
""")

def hash_pw(pw, salt):
    return hashlib.sha256((salt+pw).encode()).hexdigest()

row=cur.execute("SELECT username FROM admin_auth WHERE username='admin'").fetchone()
if not row:
    salt=secrets.token_hex(16)
    cur.execute("INSERT INTO admin_auth VALUES(?,?,?,?)",("admin",hash_pw("admin123456",salt),salt,int(time.time())))

cur.execute("INSERT OR IGNORE INTO settings VALUES('ssh_banner','Welcome to MRSSH')")
cur.execute("INSERT OR IGNORE INTO settings VALUES('support','@support')")

con.commit()
con.close()
print("admin/settings ready")
