from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Request, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import secrets, requests, os, sqlite3, hashlib, time, sqlite3, hashlib, time

app = FastAPI(title="MRSSH Stable Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TOKENS = {}
AGENT = "http://127.0.0.1:9911"
SECRET = os.getenv("MRSSH_SECRET", "change-me")

DB="/opt/mrssh-agent/mrssh.db"

def admin_hash(pw, salt):
    return hashlib.sha256((salt + pw).encode()).hexdigest()

def check_admin_password(username, password):
    if username != "admin":
        return False

    try:
        con = sqlite3.connect(DB)
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM admin_auth WHERE username='admin'").fetchone()
        con.close()
        return bool(row and row["password_hash"] == admin_hash(password, row["salt"]))
    except Exception:
        return False


class LoginReq(BaseModel):
    username: str
    password: str

class ChangePasswordReq(BaseModel):
    oldPassword: str
    newPassword: str

class UserReq(BaseModel):
    username: str
    password: str
    days: int = 30
    trafficLimitGb: float = 0
    trafficUsedGb: float = 0
    maxOnline: int = 1

class UpdateReq(BaseModel):
    password: str = ""
    days: int = 0
    trafficLimitGb: float = 0
    trafficUsedGb: float = 0
    maxOnline: int = 1

def auth(header):
    token = (header or "").replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Unauthorized")
    return True

def agent_get(path):
    r = requests.get(AGENT + path, headers={"X-Secret": SECRET}, timeout=15)
    if r.status_code != 200:
        raise HTTPException(400, r.text)
    return r.json()

def agent_post(path, payload):
    r = requests.post(AGENT + path, headers={"X-Secret": SECRET}, json=payload, timeout=15)
    if r.status_code != 200:
        raise HTTPException(400, r.text)
    return r.json()


def tg_bool(v):
    return str(v).strip().lower() in ("1","true","yes","on")

def tg_settings():
    import sqlite3
    DB="/opt/mrssh-agent/mrssh.db"
    con=sqlite3.connect(DB)
    con.execute("""
    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT
    )
    """)
    rows=con.execute("SELECT key,value FROM settings").fetchall()
    con.close()
    return {k:v for k,v in rows}

def tg_notify(event_key, text):
    try:
        import requests
        cfg=tg_settings()

        if not tg_bool(cfg.get("telegramEnabled")):
            print("TG skip: disabled", flush=True)
            return False

        if not tg_bool(cfg.get(event_key, "true")):
            print("TG skip: event disabled " + event_key, flush=True)
            return False

        token=cfg.get("telegramBotToken","").strip()
        chat_id=cfg.get("telegramChatId","").strip()

        if not token or not chat_id:
            print("TG skip: missing token/chat", flush=True)
            return False

        r=requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id":chat_id,"text":text,"parse_mode":"HTML"},
            timeout=8
        )
        print("TG sent:", r.status_code, r.text[:200], flush=True)
        return r.ok
    except Exception as e:
        print("TG error:", repr(e), flush=True)
        return False


@app.get("/health")
def health():
    return {"ok": True}

def ip_info(ip):
    try:
        r = requests.get(f"https://ipwho.is/{ip}", timeout=5).json()
        return r.get("country","Unknown"), r.get("city","Unknown")
    except Exception:
        return "Unknown", "Unknown"

@app.post("/auth/login")
def login(req: LoginReq, request: Request):
    ip = request.headers.get("x-forwarded-for", request.client.host)
    country, city = ip_info(ip)
    if check_admin_password(req.username, req.password):
        tg_notify("telegramNotifyAdminLogin", f"⭐ <b>Admin Login</b>\n👤 Username: <code>{req.username}</code>\n🌍 IP: <code>{ip}</code>\n🏳️ Country: {country}\n🏙 City: {city}")
        token = secrets.token_hex(32)
        TOKENS[token] = True
        return {"access_token": token}
    tg_notify("telegramNotifyAdminLoginFailed", f"🚨 <b>Admin Login Failed</b>\n👤 Username: <code>{req.username}</code>\n🌍 IP: <code>{ip}</code>\n🏳️ Country: {country}\n🏙 City: {city}")
    raise HTTPException(401, "bad login")


@app.post("/auth/change-password")
def change_password(req: ChangePasswordReq, authorization: str = Header(None)):
    auth(authorization)

    if not check_admin_password("admin", req.oldPassword):
        raise HTTPException(400, "Old password is wrong")

    if len(req.newPassword) < 8:
        raise HTTPException(400, "New password must be at least 8 characters")

    import secrets as sec
    salt = sec.token_hex(16)
    password_hash = admin_hash(req.newPassword, salt)

    con = sqlite3.connect(DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS admin_auth (
          username TEXT PRIMARY KEY,
          password_hash TEXT NOT NULL,
          salt TEXT NOT NULL,
          updated_at INTEGER NOT NULL
        )
    """)
    con.execute("""
        INSERT INTO admin_auth(username,password_hash,salt,updated_at)
        VALUES('admin',?,?,?)
        ON CONFLICT(username) DO UPDATE SET
          password_hash=excluded.password_hash,
          salt=excluded.salt,
          updated_at=excluded.updated_at
    """, (password_hash, salt, int(time.time())))
    con.commit()
    con.close()

    return {"ok": True}


@app.get("/users")
def users(authorization: str = Header(None)):
    auth(authorization)

    from datetime import datetime, date

    data = agent_get("/users")

    def expired(exp):
        if not exp or str(exp).lower()=="never":
            return False
        try:
            d=datetime.strptime(exp.strip(), "%b %d, %Y").date()
            return date.today() > d
        except:
            return False

    for u in data:
        reason="active"

        if expired(u.get("expire")):
            reason="expired"
        elif u.get("trafficLimited"):
            reason="traffic_limited"
        elif u.get("status")=="suspended":
            reason="manual_disabled"

        u["statusReason"]=reason
        u["statusLabel"]={
            "active":"Active",
            "expired":"Expired",
            "traffic_limited":"Traffic Limited",
            "manual_disabled":"Disabled"
        }.get(reason,"Active")

    return data


@app.get("/dashboard")
def dashboard(authorization: str = Header(None)):
    auth(authorization)
    return agent_get("/dashboard")

@app.post("/users")
def create_user(req: UserReq, node_ids: str | None = None, authorization: str = Header(None)):
    auth(authorization)

    import sqlite3, requests

    targets=[]

    if not node_ids:
        targets=[{
            "id":0,
            "name":"Local Master",
            "local":True
        }]
    else:
        ids=[x.strip() for x in node_ids.split(",") if x.strip()]

        DB="/opt/mrssh-agent/mrssh.db"

        con=sqlite3.connect(DB)
        con.row_factory=sqlite3.Row

        for nid in ids:
            if nid=="0":
                targets.append({
                    "id":0,
                    "name":"Local Master",
                    "local":True
                })
                continue

            row=con.execute("SELECT * FROM nodes WHERE id=?", (nid,)).fetchone()

            if row:
                targets.append({
                    "id":row["id"],
                    "name":row["name"],
                    "base_url":row["base_url"],
                    "token":row["token"],
                    "local":False
                })

        con.close()

    results=[]

    for t in targets:
        try:
            if t["local"]:
                result=agent_post("/create-user", req.dict())
            else:
                r=requests.post(
                    t["base_url"]+"/create-user",
                    headers={"X-Secret": t["token"]},
                    json=req.dict(),
                    timeout=20
                )

                result=r.json()

            results.append({
                "server":t["name"],
                "ok":True,
                "result":result
            })

        except Exception as e:
            results.append({
                "server":t["name"],
                "ok":False,
                "error":str(e)
            })

    try:
        ok_count = sum(1 for x in results if x.get("ok"))
        print("TG create hook reached", ok_count, flush=True)
        if ok_count:
            try:
                import sqlite3
                con=sqlite3.connect("/opt/mrssh-agent/mrssh.db")
                try:
                    con.execute("ALTER TABLE users_meta ADD COLUMN password_plain TEXT DEFAULT ''")
                    con.commit()
                except Exception:
                    pass
                con.execute("UPDATE users_meta SET password_plain=? WHERE username=?", (req.password, req.username))
                con.commit()
                con.close()
            except Exception as e:
                print("password_plain backend create error:", repr(e), flush=True)

            tg_notify(
                "telegramNotifyUserCreated",
                f"✅ <b>User Created</b>\nUsername: <code>{req.username}</code>\nDays: {req.days}\nTraffic: {req.trafficLimitGb} GB\nServers: {ok_count}"
            )
    except Exception:
        pass

    return results

@app.put("/users/{username}")
def update_user(username: str, req: UpdateReq, authorization: str = Header(None)):
    auth(authorization)

    def find_user():
        try:
            users = agent_get("/users")
            for u in users:
                if u.get("username") == username:
                    return u
        except Exception:
            pass
        return {}

    old = find_user()

    payload = {"username": username, **req.dict()}
    res = agent_post("/update-user", payload)

    new = find_user()

    try:
        changes = []

        if getattr(req, "password", None):
            tg_notify(
                "telegramNotifyPasswordChanged",
                "🔑 <b>Password Changed</b>\n👤 Username: <code>" + username + "</code>"
            )

        old_expire = str(old.get("expire", ""))
        new_expire = str(new.get("expire", ""))
        if old_expire and new_expire and old_expire != new_expire:
            changes.append("📅 Expire: " + old_expire + " → " + new_expire)

        old_limit = old.get("trafficLimitGb")
        new_limit = new.get("trafficLimitGb")
        if old_limit is not None and new_limit is not None and float(old_limit) != float(new_limit):
            changes.append("📊 Traffic Limit: " + str(old_limit) + " GB → " + str(new_limit) + " GB")

        old_max = old.get("maxOnline")
        new_max = new.get("maxOnline")
        if old_max is not None and new_max is not None and int(old_max) != int(new_max):
            changes.append("🔗 Connection Limit: " + str(old_max) + " → " + str(new_max))

        if changes:
            tg_notify(
                "telegramNotifyUserUpdated",
                "✏️ <b>User Updated</b>\n👤 Username: <code>" + username + "</code>\n" + "\n".join(changes)
            )
    except Exception as e:
        print("TG update error:", repr(e), flush=True)

    return res


@app.delete("/users/{username}")
def delete_user(username: str, authorization: str = Header(None)):
    auth(authorization)
    res = agent_post("/delete-user", {"username": username})
    tg_notify("telegramNotifyUserDeleted", f"🗑 <b>User Deleted</b>\nUsername: <code>{username}</code>")
    return res

@app.post("/users/{username}/suspend")
def suspend_user(username: str, authorization: str = Header(None)):
    auth(authorization)
    return agent_post("/suspend-user", {"username": username})

@app.post("/users/{username}/activate")
def activate_user(username: str, authorization: str = Header(None)):
    auth(authorization)
    return agent_post("/activate-user", {"username": username})

@app.post("/users/{username}/reset-traffic")
def reset_traffic(username: str, authorization: str = Header(None)):
    auth(authorization)

    res = agent_post("/reset-traffic", {"username": username})

    tg_notify(
        "telegramNotifyTrafficReset",
        f"🔄 <b>Traffic Reset</b>\n👤 Username: <code>{username}</code>\n📊 Used traffic reset to 0"
    )

    return res

@app.post("/users/{username}/kill-session")
def kill_session(username: str, payload: dict, authorization: str = Header(None)):
    auth(authorization)
    return agent_post("/kill-session", {"username": username, "pid": payload.get("pid")})

@app.get("/logs")
def logs(authorization: str = Header(None)):
    auth(authorization)

    import sqlite3
    DB="/opt/mrssh-agent/mrssh.db"

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    rows = con.execute("""
        SELECT id, actor, action, username, detail, created_at
        FROM audit_logs
        ORDER BY id DESC
        LIMIT 100
    """).fetchall()

    con.close()

    return [dict(r) for r in rows]

@app.get("/system")
def system_stats(authorization: str = Header(None)):
    auth(authorization)

    import psutil,time

    vm=psutil.virtual_memory()
    disk=psutil.disk_usage('/')

    net1=psutil.net_io_counters()
    time.sleep(1)
    net2=psutil.net_io_counters()

    rx_bps=net2.bytes_recv-net1.bytes_recv
    tx_bps=net2.bytes_sent-net1.bytes_sent

    def speed_text(b):
        if b >= 1024*1024:
            return f"{b/1024/1024:.2f} MB/s"
        if b >= 1024:
            return f"{b/1024:.1f} KB/s"
        return f"{b} B/s"

    return {
        "cpu": round(psutil.cpu_percent(),1),

        "ramPercent": round(vm.percent,1),
        "ramUsedGb": round(vm.used/1024/1024/1024,2),
        "ramTotalGb": round(vm.total/1024/1024/1024,2),

        "diskPercent": round(disk.percent,1),
        "diskUsedGb": round(disk.used/1024/1024/1024,2),
        "diskTotalGb": round(disk.total/1024/1024/1024,2),

        "downloadMbps": round(rx_bps/1024/1024,3),
        "uploadMbps": round(tx_bps/1024/1024,3),
        "downloadText": speed_text(rx_bps),
        "uploadText": speed_text(tx_bps)
    }

@app.get("/top-users")
def top_users(authorization: str = Header(None)):
    auth(authorization)

    users_data = agent_get("/users")

    sorted_users = sorted(
        users_data,
        key=lambda u: float(u.get("trafficUsedGb", 0) or 0),
        reverse=True
    )

    return sorted_users[:5]

@app.get("/security")
def security_status(authorization: str = Header(None)):
    auth(authorization)
    return agent_get("/security")


@app.post("/security/unban/{ip}")
def unban_ip(ip: str, authorization: str = Header(None)):
    auth(authorization)

    import subprocess

    subprocess.run(
        ["fail2ban-client","set","sshd","unbanip",ip],
        check=False
    )

    return {"ok":True}

import tarfile,datetime,shutil,os,json,pwd,spwd,subprocess,tempfile

BACKUP_DIR="/opt/mrssh-backups"

def collect_linux_users():
    users=[]

    for p in pwd.getpwall():
        if p.pw_uid < 1000:
            continue

        if p.pw_shell.endswith("nologin"):
            continue

        try:
            shadow=spwd.getspnam(p.pw_name)
            passwd_hash=shadow.sp_pwdp
        except:
            passwd_hash=""

        users.append({
            "username":p.pw_name,
            "uid":p.pw_uid,
            "home":p.pw_dir,
            "shell":p.pw_shell,
            "passwordHash":passwd_hash
        })

    for u in users:
        r=detect_reason(u)
        u["statusReason"]=r

        labels={
            "active":"Active",
            "traffic_limited":"Traffic Limited",
            "expired":"Expired"
        }

        u["statusLabel"]=labels.get(r,"Active")

    return users


@app.post("/backup/create")
def create_backup(authorization: str = Header(None)):
    auth(authorization)

    ts=datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

    tmp=tempfile.mkdtemp(prefix="mrssh-backup-")

    shutil.copy("/opt/mrssh-agent/mrssh.db", tmp+"/mrssh.db")

    with open(tmp+"/linux_users.json","w") as f:
        json.dump(collect_linux_users(),f)

    with open(tmp+"/manifest.json","w") as f:
        json.dump({
            "createdAt": ts,
            "version":"MRSSH v4"
        },f)

    out=f"{BACKUP_DIR}/mrssh-backup-{ts}.tar.gz"

    with tarfile.open(out,"w:gz") as tar:
        tar.add(tmp,arcname="mrssh-backup")

    shutil.rmtree(tmp)

    return {
        "ok":True,
        "file":os.path.basename(out)
    }


@app.get("/backup/list")
def list_backups(authorization: str = Header(None)):
    auth(authorization)

    files=[]

    for f in sorted(os.listdir(BACKUP_DIR),reverse=True):
        path=f"{BACKUP_DIR}/{f}"

        if not os.path.isfile(path):
            continue

        files.append({
            "name":f,
            "sizeMb":round(os.path.getsize(path)/1024/1024,2)
        })

    return files

@app.get("/backup/download/{filename}")
def download_backup(filename: str, authorization: str = Header(None)):
    auth(authorization)

    from fastapi.responses import FileResponse
    import os

    safe = os.path.basename(filename)
    path = f"/opt/mrssh-backups/{safe}"

    if not os.path.exists(path):
        raise HTTPException(404, "backup not found")

    return FileResponse(
        path,
        media_type="application/gzip",
        filename=safe
    )


@app.get("/backup/list2")
def backup_list2(authorization: str = Header(None)):
    auth(authorization)
    return agent_get("/backup/list")


@app.post("/backup/create2")
def backup_create2(authorization: str = Header(None)):
    auth(authorization)
    return agent_post("/backup/create", {})


@app.post("/backup/delete")
def backup_delete(payload: dict, authorization: str = Header(None)):
    auth(authorization)
    return agent_post("/backup/delete", {"filename": payload.get("filename")})


@app.post("/backup/restore")
def backup_restore(payload: dict, authorization: str = Header(None)):
    auth(authorization)
    return agent_post("/backup/restore", {"filename": payload.get("filename")})


@app.post("/backup/upload")
async def backup_upload(file: UploadFile = File(...), authorization: str = Header(None)):
    auth(authorization)

    import os, shutil
    os.makedirs("/opt/mrssh-backups", exist_ok=True)

    safe=os.path.basename(file.filename)
    if not safe.endswith(".tar.gz"):
        raise HTTPException(400, "Only .tar.gz backup files are allowed")

    path=f"/opt/mrssh-backups/{safe}"
    with open(path,"wb") as f:
        shutil.copyfileobj(file.file,f)

    return {"ok": True, "file": safe}


@app.get("/backup/download2/{filename}")
def backup_download2(filename: str, authorization: str = Header(None)):
    auth(authorization)

    from fastapi.responses import FileResponse
    import os

    safe=os.path.basename(filename)
    path=f"/opt/mrssh-backups/{safe}"

    if not os.path.exists(path):
        raise HTTPException(404, "backup not found")

    return FileResponse(path, media_type="application/gzip", filename=safe)


@app.get("/autobackup/status")
def autobackup_status_api(authorization: str = Header(None)):
    auth(authorization)
    return agent_get("/autobackup/status")


@app.post("/autobackup/toggle")
def autobackup_toggle_api(payload: dict, authorization: str = Header(None)):
    auth(authorization)
    return agent_post("/autobackup/toggle", {
        "enabled": payload.get("enabled", False)
    })


@app.get("/sessions")
def sessions(authorization: str = Header(None)):
    auth(authorization)

    users_data = agent_get("/users")
    out = []

    for u in users_data:
        for session in u.get("sessions", []):
            out.append({
                "username": u.get("username"),
                "ip": session.get("ip", "-"),
                "isp": session.get("isp", "-"),
                "country": session.get("country", "-"),
                "city": session.get("city", "-"),
                "pid": session.get("pid", "-"),
                "source": session.get("source", "-"),
                "trafficUsedText": u.get("trafficUsedText", "0 KB"),
                "trafficLimitText": u.get("trafficLimitText", "unlimited"),
                "connections": u.get("connections", "0/1"),
            })

    return out

@app.get("/nodes")
def list_nodes(authorization: str = Header(None)):
    auth(authorization)

    import sqlite3, time
    DB="/opt/mrssh-agent/mrssh.db"

    con=sqlite3.connect(DB)
    con.row_factory=sqlite3.Row
    con.execute("""
    CREATE TABLE IF NOT EXISTS nodes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      base_url TEXT NOT NULL,
      token TEXT NOT NULL,
      enabled INTEGER DEFAULT 1,
      created_at INTEGER NOT NULL
    )
    """)
    rows=con.execute("SELECT id,name,base_url,enabled,created_at FROM nodes ORDER BY id DESC").fetchall()
    con.close()

    return [dict(r) for r in rows]


@app.post("/nodes")
def add_node(payload: dict, authorization: str = Header(None)):
    auth(authorization)

    import sqlite3, time
    DB="/opt/mrssh-agent/mrssh.db"

    name=payload.get("name","").strip()
    base_url=payload.get("base_url","").strip().rstrip("/")
    token=payload.get("token","").strip()

    if not name or not base_url or not token:
        raise HTTPException(400, "name, base_url and token are required")

    con=sqlite3.connect(DB)
    con.execute("""
    CREATE TABLE IF NOT EXISTS nodes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      base_url TEXT NOT NULL,
      token TEXT NOT NULL,
      enabled INTEGER DEFAULT 1,
      created_at INTEGER NOT NULL
    )
    """)
    con.execute(
        "INSERT INTO nodes(name,base_url,token,enabled,created_at) VALUES(?,?,?,?,?)",
        (name,base_url,token,1,int(time.time()))
    )
    con.commit()
    con.close()

    return {"ok": True}


@app.delete("/nodes/{node_id}")
def delete_node(node_id: int, authorization: str = Header(None)):
    auth(authorization)

    import sqlite3
    DB="/opt/mrssh-agent/mrssh.db"

    con=sqlite3.connect(DB)
    con.execute("DELETE FROM nodes WHERE id=?", (node_id,))
    con.commit()
    con.close()

    return {"ok": True}


@app.post("/nodes/{node_id}/test")
def test_node(node_id: int, authorization: str = Header(None)):
    auth(authorization)

    import sqlite3, requests
    DB="/opt/mrssh-agent/mrssh.db"

    con=sqlite3.connect(DB)
    con.row_factory=sqlite3.Row
    row=con.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
    con.close()

    if not row:
        raise HTTPException(404, "node not found")

    try:
        r=requests.get(
            row["base_url"] + "/health",
            headers={"X-Secret": row["token"]},
            timeout=5
        )
        if r.status_code == 200:
            return {"ok": True, "response": r.json()}
        return {"ok": False, "status": r.status_code, "body": r.text}
    except Exception as e:
        return {"ok": False, "error": str(e)}





@app.post("/users/{username}/manual-disable")
def manual_disable_user(username: str, authorization: str = Header(None)):
    auth(authorization)
    return agent_post("/manual-disable", {"username": username})


@app.post("/users/{username}/manual-enable")
def manual_enable_user(username: str, authorization: str = Header(None)):
    auth(authorization)
    return agent_post("/manual-enable", {"username": username})


@app.get("/settings")
def get_settings(authorization: str = Header(None)):
    auth(authorization)
    import sqlite3
    DB="/opt/mrssh-agent/mrssh.db"
    con=sqlite3.connect(DB)
    con.execute("""
    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT
    )
    """)
    rows=con.execute("SELECT key,value FROM settings").fetchall()
    con.close()
    return {k:v for k,v in rows}


@app.post("/settings")
def save_settings(payload: dict, authorization: str = Header(None)):
    auth(authorization)
    import sqlite3
    DB="/opt/mrssh-agent/mrssh.db"
    con=sqlite3.connect(DB)
    con.execute("""
    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT
    )
    """)
    for k,v in payload.items():
        con.execute(
          "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
          (k,str(v))
        )
    con.commit()
    con.close()
    return {"ok": True}


@app.get("/security/banned-ips")
def banned_ips(authorization: str = Header(None)):
    auth(authorization)
    return agent_get("/fail2ban/banned-ips")


@app.post("/security/unban")
def unban_ip(data: dict, authorization: str = Header(None)):
    auth(authorization)
    return agent_post("/fail2ban/unban", data)


@app.post("/telegram/test")
def telegram_test(authorization: str = Header(None)):
    auth(authorization)

    import sqlite3, requests
    DB="/opt/mrssh-agent/mrssh.db"

    con=sqlite3.connect(DB)
    rows=con.execute("SELECT key,value FROM settings").fetchall()
    con.close()

    cfg={k:v for k,v in rows}
    token=cfg.get("telegramBotToken","").strip()
    chat_id=cfg.get("telegramChatId","").strip()

    if not token or not chat_id:
        raise HTTPException(400,"telegramBotToken and telegramChatId required")

    r=requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id":chat_id,
            "text":"✅ MRSSH Telegram test notification",
            "parse_mode":"HTML"
        },
        timeout=10
    )

    if not r.ok:
        raise HTTPException(400,r.text)

    return {"ok":True}

@app.post("/users/{username}/save-password")
def save_user_password(username: str, data: dict, authorization: str = Header(None)):
    auth(authorization)

    import sqlite3
    password = str(data.get("password", ""))

    if not password:
        return {"ok": True, "saved": False}

    DB="/opt/mrssh-agent/mrssh.db"
    con=sqlite3.connect(DB)
    try:
        con.execute("ALTER TABLE users_meta ADD COLUMN password_plain TEXT DEFAULT ''")
        con.commit()
    except Exception:
        pass

    con.execute("UPDATE users_meta SET password_plain=? WHERE username=?", (password, username))
    con.commit()
    con.close()

    return {"ok": True, "saved": True}
