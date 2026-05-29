import sqlite3, json, os, time

DB="/opt/mrssh-agent/mrssh.db"
META="/opt/mrssh-agent/users_meta.json"

con=sqlite3.connect(DB)
cur=con.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users_meta (
  username TEXT PRIMARY KEY,
  traffic_limit_gb REAL DEFAULT 0,
  traffic_used_gb REAL DEFAULT 0,
  max_online INTEGER DEFAULT 1,
  traffic_limited INTEGER DEFAULT 0,
  password_plain TEXT DEFAULT '',
  traffic_download_gb REAL DEFAULT 0,
  traffic_upload_gb REAL DEFAULT 0,
  manual_disabled INTEGER DEFAULT 0,
  created_at INTEGER DEFAULT 0,
  updated_at INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor TEXT DEFAULT 'system',
  action TEXT NOT NULL,
  username TEXT,
  detail TEXT,
  created_at INTEGER NOT NULL
)
""")

if os.path.exists(META):
    try:
        data=json.load(open(META))
        now=int(time.time())
        for username, m in data.items():
            cur.execute("""
            INSERT OR REPLACE INTO users_meta
            (username, traffic_limit_gb, traffic_used_gb, max_online, traffic_limited, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM users_meta WHERE username=?), ?), ?)
            """, (
                username,
                float(m.get("trafficLimitGb",0) or 0),
                float(m.get("trafficUsedGb",0) or 0),
                int(m.get("maxOnline",1) or 1),
                1 if m.get("trafficLimited") else 0,
                username,
                now,
                now
            ))
    except Exception as e:
        print("migration warning:", e)

con.commit()
con.close()
print("SQLite ready:", DB)


for col, typ in [
    ("password_plain", "TEXT DEFAULT ''"),
    ("traffic_download_gb", "REAL DEFAULT 0"),
    ("traffic_upload_gb", "REAL DEFAULT 0"),
    ("manual_disabled", "INTEGER DEFAULT 0"),
]:
    try:
        cur.execute(f"ALTER TABLE users_meta ADD COLUMN {col} {typ}")
    except Exception:
        pass

con.commit()
print("SQLite migrated columns ready")
