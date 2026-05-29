from http.server import BaseHTTPRequestHandler, HTTPServer
import json, subprocess, datetime, pwd, os, urllib.request, sqlite3, time

def load_secret():
    for path in ("/opt/mrssh-agent/.env", "/root/MRSSH/.env"):
        try:
            for line in open(path):
                if line.startswith("MRSSH_SECRET="):
                    return line.strip().split("=",1)[1]
        except Exception:
            pass
    return "change-me"

SECRET=load_secret()
DB="/opt/mrssh-agent/mrssh.db"
ISP_CACHE="/opt/mrssh-agent/isp_cache.json"

IGNORE={"root","daemon","bin","sys","sync","games","man","lp","mail","news","uucp","proxy","www-data","backup","list","irc","gnats","nobody","systemd-network","systemd-resolve","messagebus","sshd","_apt","lxd","uuidd","dnsmasq","landscape","fwupd","pollinate","syslog"}

def db():
    con=sqlite3.connect(DB)
    con.row_factory=sqlite3.Row
    return con

def ensure_db():
    con=db(); cur=con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users_meta (
      username TEXT PRIMARY KEY,
      traffic_limit_gb REAL DEFAULT 0,
      traffic_used_gb REAL DEFAULT 0,
      max_online INTEGER DEFAULT 1,
      traffic_limited INTEGER DEFAULT 0,
      password_plain TEXT DEFAULT '',
      created_at INTEGER DEFAULT 0,
      updated_at INTEGER DEFAULT 0
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS audit_logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      actor TEXT DEFAULT 'system',
      action TEXT NOT NULL,
      username TEXT,
      detail TEXT,
      created_at INTEGER NOT NULL
    )""")
    con.commit(); con.close()

def log(action, username="", detail=""):
    con=db()
    con.execute("INSERT INTO audit_logs(actor,action,username,detail,created_at) VALUES(?,?,?,?,?)",
                ("admin",action,username,detail,int(time.time())))
    con.commit(); con.close()

def get_meta(username):
    con=db()
    row=con.execute("SELECT * FROM users_meta WHERE username=?", (username,)).fetchone()
    con.close()
    if not row:
        return {"trafficLimitGb":0,"trafficUsedGb":0,"maxOnline":1,"trafficLimited":False}
    return {
        "trafficLimitGb":float(row["traffic_limit_gb"] or 0),
        "trafficUsedGb":float(row["traffic_used_gb"] or 0),
        "trafficUploadGb":float(row["traffic_upload_gb"] or 0) if "traffic_upload_gb" in row.keys() else 0,
        "trafficDownloadGb":float(row["traffic_download_gb"] or 0) if "traffic_download_gb" in row.keys() else 0,
        "maxOnline":int(row["max_online"] or 1),
        "trafficLimited":bool(row["traffic_limited"]), "passwordPlain": row["password_plain"] if "password_plain" in row.keys() else "",
        "manualDisabled": bool(row["manual_disabled"]) if "manual_disabled" in row.keys() else False
    }

def set_meta(username, trafficLimitGb=None, trafficUsedGb=None, maxOnline=None, trafficLimited=None):
    old=get_meta(username)
    tl = old["trafficLimitGb"] if trafficLimitGb is None else float(trafficLimitGb or 0)
    tu = old["trafficUsedGb"] if trafficUsedGb is None else float(trafficUsedGb or 0)
    mo = old["maxOnline"] if maxOnline is None else int(maxOnline or 1)
    lim = old["trafficLimited"] if trafficLimited is None else bool(trafficLimited)
    now=int(time.time())
    con=db()
    con.execute("""
      INSERT INTO users_meta(username, traffic_limit_gb, traffic_used_gb, max_online, traffic_limited, created_at, updated_at)
      VALUES(?,?,?,?,?,?,?)
      ON CONFLICT(username) DO UPDATE SET
        traffic_limit_gb=excluded.traffic_limit_gb,
        traffic_used_gb=excluded.traffic_used_gb,
        max_online=excluded.max_online,
        traffic_limited=excluded.traffic_limited,
        updated_at=excluded.updated_at
    """, (username,tl,tu,mo,1 if lim else 0,now,now))
    con.commit(); con.close()

def delete_meta(username):
    con=db()
    con.execute("DELETE FROM users_meta WHERE username=?", (username,))
    con.commit(); con.close()

def send(h,c,d):
    h.send_response(c)
    h.send_header("Content-Type","application/json")
    h.end_headers()
    h.wfile.write(json.dumps(d).encode())

def run(cmd):
    return subprocess.run(cmd,capture_output=True,text=True)

def is_user_expired(username):
    try:
        out = expiry(username)
        if not out or out.lower() == "never":
            return False

        import datetime
        for fmt in ("%b %d, %Y", "%Y-%m-%d", "%d %b %Y"):
            try:
                d = datetime.datetime.strptime(out, fmt).date()
                return datetime.date.today() > d
            except:
                pass

        return False
    except Exception:
        return False


def format_traffic(gb):
    gb=float(gb or 0)
    mb=gb*1024
    kb=mb*1024
    if gb>=1: return f"{gb:.2f} GB"
    if mb>=1: return f"{mb:.2f} MB"
    return f"{kb:.0f} KB"

def load_json(path, default):
    try: return json.load(open(path))
    except: return default

def save_json(path, data):
    json.dump(data, open(path,"w"), indent=2)

def lookup_isp(ip):
    if not ip or ip=="-" or ip.startswith(("10.","192.168.","172.")):
        return {"ip":ip or "-", "isp":"local/private", "country":"-", "city":"-", "org":"-"}
    cache=load_json(ISP_CACHE,{})
    if ip in cache: return cache[ip]
    try:
        url=f"http://ip-api.com/json/{ip}?fields=status,country,city,isp,org,query"
        with urllib.request.urlopen(url,timeout=3) as r:
            d=json.loads(r.read().decode())
        item={"ip":ip,"isp":"unknown","country":"-","city":"-","org":"-"}
        if d.get("status")=="success":
            item={"ip":d.get("query",ip),"isp":d.get("isp","-"),"org":d.get("org","-"),"country":d.get("country","-"),"city":d.get("city","-")}
    except Exception:
        item={"ip":ip,"isp":"lookup failed","country":"-","city":"-","org":"-"}
    cache[ip]=item
    save_json(ISP_CACHE,cache)
    return item

def expiry(username):
    return run(["bash","-lc",f"chage -l {username} | grep 'Account expires' | cut -d: -f2-"]).stdout.strip() or "never"

def status(username):
    x=run(["bash","-lc",f"passwd -S {username} | awk '{{print $2}}'"]).stdout.strip()
    return "suspended" if x in ["L","LK"] else "active"

def online_info():
    data={}
    out=run(["bash","-lc","ps -eo pid,args | grep 'sshd:' | grep -v grep"]).stdout.strip()
    for line in out.splitlines():
        parts=line.strip().split(None,1)
        if len(parts)<2: continue
        pid,args=parts
        if "sshd:" not in args: continue
        tail=args.split("sshd:",1)[1].strip()
        if tail.startswith("/"): continue
        user=tail.split()[0].split("@")[0].strip()
        if not user or user=="root": continue

        ip="-"
        ssout=run(["bash","-lc",f"ss -tnp | grep 'pid={pid},' | grep ':22 ' | head -1"]).stdout.strip()
        if ssout:
            cols=ssout.split()
            if len(cols)>=5:
                ip=cols[4].rsplit(":",1)[0]

        if any(x.get("ip")==ip and ip!="-" for x in data.get(user,[])):
            continue
        data.setdefault(user,[]).append({**lookup_isp(ip),"loginAt":"online","pid":pid,"source":"ss"})
    return data

def users():
    online=online_info()
    out=[]
    for u in pwd.getpwall():
        if u.pw_name in IGNORE or u.pw_uid<1000: continue
        if "nologin" in u.pw_shell or "false" in u.pw_shell: continue
        m=get_meta(u.pw_name)
        limit=m["trafficLimitGb"]; used=m["trafficUsedGb"]; maxo=m["maxOnline"]
        sessions=online.get(u.pw_name,[])
        out.append({
            "username":u.pw_name,"uid":u.pw_uid,"home":u.pw_dir,"shell":u.pw_shell,
            "status":status(u.pw_name),"expire":expiry(u.pw_name),
            "trafficLimitGb":limit,"trafficUsedGb":used,
            "trafficUploadGb":m.get("trafficUploadGb",0),
            "trafficDownloadGb":m.get("trafficDownloadGb",0),
            "trafficUsedText":format_traffic(used),
            "trafficUploadText":format_traffic(m.get("trafficUploadGb",0)),
            "trafficDownloadText":format_traffic(m.get("trafficDownloadGb",0)),
            "trafficLimitText":format_traffic(limit) if limit>0 else "unlimited",
            "trafficPercent":round((used/limit)*100,1) if limit>0 else 0,            "online":len(sessions)>0,"onlineCount":len(sessions),"sessions":sessions,
              "maxOnline":maxo,"connections":f"{len(sessions)}/{maxo}","passwordPlain":m.get("passwordPlain","")
        })
    return sorted(out,key=lambda x:x["uid"],reverse=True)

def dashboard():
    u=users()
    return {"total":len(u),"online":len([x for x in u if x["online"]]),"active":len([x for x in u if x["status"]=="active"]),"expired":0,"suspended":len([x for x in u if x["status"]=="suspended"])}


def fail2ban_status():
    import re
    try:
        out = subprocess.check_output(["fail2ban-client","status","sshd"], text=True)
    except Exception as e:
        return {"active": False, "error": str(e), "bannedIps": []}

    data = {"active": True, "currentFailed":0, "totalFailed":0, "currentBanned":0, "totalBanned":0, "bannedIps":[]}

    for line in out.splitlines():
        line=line.strip()
        nums=re.findall(r"\d+", line)
        if "Currently failed:" in line and nums: data["currentFailed"]=int(nums[0])
        elif "Total failed:" in line and nums: data["totalFailed"]=int(nums[0])
        elif "Currently banned:" in line and nums: data["currentBanned"]=int(nums[0])
        elif "Total banned:" in line and nums: data["totalBanned"]=int(nums[0])
        elif "Banned IP list:" in line:
            data["bannedIps"]=line.split(":",1)[1].strip().split()

    return data


BACKUP_DIR="/opt/mrssh-backups"

def backup_list():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    out=[]
    for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
        path=os.path.join(BACKUP_DIR,f)
        if not os.path.isfile(path): 
            continue
        size=os.path.getsize(path)
        if size >= 1024*1024:
            sizeText=f"{size/1024/1024:.2f} MB"
        elif size >= 1024:
            sizeText=f"{size/1024:.1f} KB"
        else:
            sizeText=f"{size} B"
        out.append({"name":f,"size":size,"sizeText":sizeText})
    return out

def backup_create():
    import tarfile, tempfile, shutil, spwd
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts=datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    tmp=tempfile.mkdtemp(prefix="mrssh-data-")

    shutil.copy(DB, tmp+"/mrssh.db")

    users=[]
    for u in pwd.getpwall():
        if u.pw_uid < 1000 or u.pw_name in IGNORE:
            continue
        if "nologin" in u.pw_shell or "false" in u.pw_shell:
            continue
        try:
            ph=spwd.getspnam(u.pw_name).sp_pwdp
        except:
            ph=""
        users.append({
            "username":u.pw_name,
            "home":u.pw_dir,
            "shell":u.pw_shell,
            "passwordHash":ph,
            "expire":expiry(u.pw_name)
        })

    json.dump(users, open(tmp+"/linux_users.json","w"), indent=2)
    json.dump({"version":"MRSSH-DATA-1","createdAt":ts}, open(tmp+"/manifest.json","w"), indent=2)

    out=f"{BACKUP_DIR}/mrssh-data-{ts}.tar.gz"
    with tarfile.open(out,"w:gz") as tar:
        tar.add(tmp, arcname="mrssh-backup")
    shutil.rmtree(tmp)
    return {"ok":True,"file":os.path.basename(out)}

def backup_delete(name):
    safe=os.path.basename(name)
    path=os.path.join(BACKUP_DIR,safe)
    if os.path.exists(path):
        os.remove(path)
    return {"ok":True}

def backup_restore(name):
    import tarfile, tempfile, shutil
    safe=os.path.basename(name)
    path=os.path.join(BACKUP_DIR,safe)
    if not os.path.exists(path):
        return {"ok":False,"detail":"backup not found"}

    tmp=tempfile.mkdtemp(prefix="mrssh-restore-")
    with tarfile.open(path,"r:gz") as tar:
        tar.extractall(tmp)

    root=os.path.join(tmp,"mrssh-backup")
    db_path=os.path.join(root,"mrssh.db")
    users_path=os.path.join(root,"linux_users.json")

    if not os.path.exists(db_path) or not os.path.exists(users_path):
        shutil.rmtree(tmp)
        return {"ok":False,"detail":"invalid backup"}

    shutil.copy(db_path, DB)

    users=json.load(open(users_path))
    for u in users:
        username=u.get("username")
        if not username:
            continue

        exists=subprocess.run(["id",username],capture_output=True).returncode==0
        shell=u.get("shell") or "/bin/bash"

        if not exists:
            subprocess.run(["useradd","-m","-s",shell,username],check=False)
        else:
            subprocess.run(["usermod","-s",shell,username],check=False)

        ph=u.get("passwordHash")
        if ph:
            subprocess.run(["usermod","-p",ph,username],check=False)

        exp=u.get("expire")
        if exp and exp.lower()!="never":
            try:
                dt=datetime.datetime.strptime(exp,"%b %d, %Y").strftime("%Y-%m-%d")
                subprocess.run(["chage","-E",dt,username],check=False)
            except:
                pass

    shutil.rmtree(tmp)

    subprocess.run(["systemctl","restart","mrssh-agent"],check=False)
    subprocess.run(["systemctl","restart","mrssh-traffic"],check=False)
    subprocess.run(["systemctl","restart","mrssh-expire"],check=False)

    return {"ok":True,"restoredUsers":len(users)}


AUTO_BACKUP_CRON="/etc/cron.d/mrssh-backup"

def autobackup_status():
    return {
        "enabled": os.path.exists(AUTO_BACKUP_CRON),
        "schedule":"03:00 AM",
        "retention":5
    }

def autobackup_toggle(enabled):
    if enabled:
        open(AUTO_BACKUP_CRON,"w").write(
            "0 3 * * * root /usr/bin/python3 /opt/mrssh-agent/auto_backup.py >> /var/log/mrssh-backup.log 2>&1\n"
        )
    else:
        if os.path.exists(AUTO_BACKUP_CRON):
            os.remove(AUTO_BACKUP_CRON)

    subprocess.run(["systemctl","restart","cron"],check=False)

    return autobackup_status()

def manual_disable_user(username):
    con=sqlite3.connect(DB)
    try:
        con.execute("ALTER TABLE users_meta ADD COLUMN manual_disabled INTEGER DEFAULT 0")
        con.commit()
    except:
        pass
    con.execute("UPDATE users_meta SET manual_disabled=1 WHERE username=?", (username,))
    con.commit()
    try:
        con.execute("UPDATE users_meta SET password_plain=? WHERE username=?", (d.get("password",""), d.get("username","")))
        con.commit()
    except Exception:
        pass
    con.close()

    subprocess.run(["passwd","-l",username],check=False)
    subprocess.run(["pkill","-KILL","-u",username],check=False)

    return {"ok":True}


def manual_enable_user(username):
    con=sqlite3.connect(DB)
    try:
        con.execute("ALTER TABLE users_meta ADD COLUMN manual_disabled INTEGER DEFAULT 0")
        con.commit()
    except:
        pass
    con.execute("UPDATE users_meta SET manual_disabled=0 WHERE username=?", (username,))
    con.commit()
    con.close()

    subprocess.run(["passwd","-u",username],check=False)
    subprocess.run(["usermod","-U",username],check=False)

    return {"ok":True}


def fail2ban_banned_ips():
    out=subprocess.run("fail2ban-client status sshd",shell=True,capture_output=True,text=True).stdout
    ips=[]
    for line in out.splitlines():
        if "Banned IP list:" in line:
            ips=line.split("Banned IP list:",1)[1].split()
    return {"ips":ips}

def fail2ban_unban(ip):
    subprocess.run(["fail2ban-client","set","sshd","unbanip",ip],check=False)
    return {"ok":True}


class H(BaseHTTPRequestHandler):
    def ok(self): return self.headers.get("X-Secret")==SECRET
    def data(self): return json.loads(self.rfile.read(int(self.headers.get("Content-Length",0) or 0)) or b"{}")
    def do_GET(self):
        if not self.ok(): return send(self,403,{"detail":"forbidden"})
        if self.path=="/health": return send(self,200,{"ok":True,"role":"mrssh-node"})
        if self.path=="/fail2ban/banned-ips":
            return send(self,200,fail2ban_banned_ips())
        if self.path=="/users": return send(self,200,users())
        if self.path=="/dashboard": return send(self,200,dashboard())
        if self.path=="/security": return send(self,200,fail2ban_status())
        if self.path=="/backup/list": return send(self,200,backup_list())
        if self.path=="/autobackup/status": return send(self,200,autobackup_status())
        return send(self,404,{"detail":"not found"})
    def do_POST(self):
        if not self.ok(): return send(self,403,{"detail":"forbidden"})
        d=self.data()
        try:
            if self.path=="/backup/create":
                return send(self,200,backup_create())
            if self.path=="/backup/delete":
                return send(self,200,backup_delete(d.get("filename","")))
            if self.path=="/backup/restore":
                return send(self,200,backup_restore(d.get("filename","")))
            if self.path=="/autobackup/toggle":
                return send(self,200,autobackup_toggle(d.get("enabled",False)))
            if self.path=="/fail2ban/unban":
                return send(self,200,fail2ban_unban(d.get("ip","")))
            if self.path=="/manual-disable":
                return send(self,200,manual_disable_user(d.get("username","")))
            if self.path=="/manual-enable":
                return send(self,200,manual_enable_user(d.get("username","")))
            if self.path=="/create-user":
                u=d["username"]; p=d["password"]; days=int(d.get("days",30))
                expire=(datetime.datetime.now()+datetime.timedelta(days=days)).strftime("%Y-%m-%d")
                subprocess.run(["useradd","-m","-s","/bin/bash",u],check=True)
                hashed=subprocess.check_output(["openssl","passwd","-6",p],text=True).strip()
                subprocess.run(["usermod","-p",hashed,u],check=True)
                subprocess.run(["chage","-E",expire,u],check=True)
                set_meta(u, d.get("trafficLimitGb",0), d.get("trafficUsedGb",0), d.get("maxOnline",1), False)
                log("create_user",u)
                return send(self,200,{"ok":True,"username":u})
            if self.path=="/update-user":
                u=d["username"]
                if d.get("password"):
                    hashed=subprocess.check_output(["openssl","passwd","-6",d["password"]],text=True).strip()
                    subprocess.run(["usermod","-p",hashed,u],check=True)
                if int(d.get("days",0) or 0)>0:
                    expire=(datetime.datetime.now()+datetime.timedelta(days=int(d["days"]))).strftime("%Y-%m-%d")
                    subprocess.run(["chage","-E",expire,u],check=True)
                set_meta(u, d.get("trafficLimitGb"), d.get("trafficUsedGb"), d.get("maxOnline"))
                log("update_user",u,json.dumps(d))
                return send(self,200,{"ok":True,"username":u})
            if self.path=="/delete-user":
                u=d["username"]
                subprocess.run(["userdel","-r",u],check=True)
                delete_meta(u); log("delete_user",u)
                return send(self,200,{"ok":True})
            if self.path=="/reset-traffic":
                u=d["username"]
                set_meta(u, trafficUsedGb=0, trafficLimited=False)
                log("reset_traffic",u)
                return send(self,200,{"ok":True})
            if self.path=="/suspend-user":
                subprocess.run(["passwd","-l",d["username"]],check=True)
                log("suspend_user",d["username"])
                return send(self,200,{"ok":True})
            if self.path=="/activate-user":
                subprocess.run(["passwd","-u",d["username"]],check=True)
                log("activate_user",d["username"])
                return send(self,200,{"ok":True})
            if self.path=="/kill-session":
                pid=str(d.get("pid","")).strip()
                username=str(d.get("username","")).strip()
                if not pid.isdigit(): return send(self,400,{"detail":"invalid pid"})
                check=run(["bash","-lc",f"ps -p {pid} -o args= | grep 'sshd:' | grep '{username}'"]).stdout.strip()
                if not check: return send(self,404,{"detail":"session not found"})
                subprocess.run(["kill","-9",pid],check=False)
                log("kill_session",username,pid)
                return send(self,200,{"ok":True})
            return send(self,404,{"detail":"not found"})
        except Exception as e:
            return send(self,500,{"detail":str(e)})

ensure_db()
HTTPServer(("0.0.0.0",9911),H).serve_forever()
