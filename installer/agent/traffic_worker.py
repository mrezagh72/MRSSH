import sqlite3, subprocess, time, re

DB="/opt/mrssh-agent/mrssh.db"
GB=1024**3

def db():
    con=sqlite3.connect(DB)
    con.row_factory=sqlite3.Row
    return con

def sh(cmd):
    return subprocess.run(cmd,shell=True,capture_output=True,text=True).stdout

def ensure_cols():
    con=db()
    for col in ["traffic_download_gb","traffic_upload_gb"]:
        try:
            con.execute(f"ALTER TABLE users_meta ADD COLUMN {col} REAL DEFAULT 0")
        except:
            pass
    con.commit()
    con.close()

def ssh_sessions():
    out=sh("ps -eo pid,args | grep 'sshd:' | grep -v grep")
    sessions=[]
    for line in out.splitlines():
        parts=line.strip().split(None,1)
        if len(parts)<2: continue
        pid,args=parts
        if args.strip().startswith("/usr/sbin/sshd"): continue
        if "sshd:" not in args: continue
        tail=args.split("sshd:",1)[1].strip()
        if tail.startswith("/"): continue
        user=tail.split()[0].split("@")[0].strip()
        if user and user!="root":
            sessions.append((user,pid))
    return sessions

def pid_bytes(pid):
    out=sh(f"ss -tinp | grep -A4 'pid={pid},' 2>/dev/null")
    sent=0
    recv=0
    for m in re.finditer(r"bytes_sent:(\d+)",out):
        sent+=int(m.group(1))
    for m in re.finditer(r"bytes_received:(\d+)",out):
        recv+=int(m.group(1))
    return sent,recv

ensure_cols()
last={}

while True:
    con=db()
    rows={r["username"]:r for r in con.execute("SELECT * FROM users_meta").fetchall()}

    totals={}
    for user,pid in ssh_sessions():
        sent,recv=pid_bytes(pid)
        key=f"{user}:{pid}"
        old_sent,old_recv=last.get(key,(sent,recv))

        ds=max(0,sent-old_sent)
        dr=max(0,recv-old_recv)

        last[key]=(sent,recv)

        if ds or dr:
            totals.setdefault(user,[0,0])
            totals[user][0]+=ds
            totals[user][1]+=dr

    for user,(up_bytes,down_bytes) in totals.items():
        if user not in rows:
            continue

        row=rows[user]
        up_gb=up_bytes/GB
        down_gb=down_bytes/GB
        total_gb=up_gb+down_gb

        used=float(row["traffic_used_gb"] or 0)+total_gb
        upload=float(row["traffic_upload_gb"] or 0)+up_gb
        download=float(row["traffic_download_gb"] or 0)+down_gb

        con.execute("""
          UPDATE users_meta
          SET traffic_used_gb=?,
              traffic_upload_gb=?,
              traffic_download_gb=?,
              updated_at=strftime('%s','now')
          WHERE username=?
        """,(round(used,6),round(upload,6),round(download,6),user))

        limit=float(row["traffic_limit_gb"] or 0)
        limited=int(row["traffic_limited"] or 0)

        if limit>0 and used>=limit and not limited:
            con.execute("UPDATE users_meta SET traffic_limited=1 WHERE username=?", (user,))
            sh(f"passwd -l {user}")
            sh(f"pkill -KILL -u {user} || true")

    con.commit()
    con.close()
    time.sleep(3)
