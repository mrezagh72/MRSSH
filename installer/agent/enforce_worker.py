import sqlite3, subprocess, time, pwd, datetime

DB="/opt/mrssh-agent/mrssh.db"

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def user_exists(u):
    try:
        pwd.getpwnam(u)
        return True
    except:
        return False

def locked(u):
    out=sh(f"passwd -S {u}").stdout.split()
    return len(out)>1 and out[1]=="L"

def lock_user(u):
    sh(f"passwd -l {u} || true")
    sh(f"pkill -KILL -u {u} || true")

def unlock_user(u):
    sh(f"passwd -u {u} || true")
    sh(f"usermod -U {u} || true")

def expired(u):
    out=sh(f"chage -l {u} | grep 'Account expires' | cut -d: -f2-").stdout.strip()
    if not out or out.lower()=="never":
        return False
    try:
        d=datetime.datetime.strptime(out,"%b %d, %Y").date()
        return datetime.date.today() > d
    except:
        return False

while True:
    con=sqlite3.connect(DB)
    con.row_factory=sqlite3.Row

    try:
        con.execute("ALTER TABLE users_meta ADD COLUMN manual_disabled INTEGER DEFAULT 0")
        con.commit()
    except:
        pass

    rows=con.execute("SELECT * FROM users_meta").fetchall()

    for r in rows:
        u=r["username"]
        if not user_exists(u):
            continue

        used=float(r["traffic_used_gb"] or 0)
        limit=float(r["traffic_limit_gb"] or 0)
        manual=int(r["manual_disabled"] or 0)
        limited=int(r["traffic_limited"] or 0)

        traffic_blocked = limit > 0 and used >= limit
        date_blocked = expired(u)
        manual_blocked = manual == 1

        should_lock = traffic_blocked or date_blocked or manual_blocked

        if traffic_blocked and not limited:
            con.execute("UPDATE users_meta SET traffic_limited=1 WHERE username=?", (u,))
        elif not traffic_blocked and limited:
            con.execute("UPDATE users_meta SET traffic_limited=0 WHERE username=?", (u,))

        if should_lock and not locked(u):
            lock_user(u)

        if not should_lock and locked(u):
            unlock_user(u)

    con.commit()
    con.close()
    time.sleep(10)
