import subprocess, time, pwd, datetime

IGNORE = {
    "root","daemon","bin","sys","sync","games","man","lp","mail","news",
    "uucp","proxy","www-data","backup","list","irc","gnats","nobody",
    "systemd-network","systemd-resolve","messagebus","sshd","_apt"
}

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)

def expire_date(username):
    out = run(["bash","-lc",f"chage -l {username} | grep 'Account expires' | cut -d: -f2-"]).stdout.strip()
    if not out or out == "never":
        return None
    try:
        return datetime.datetime.strptime(out, "%b %d, %Y").date()
    except:
        return None

while True:
    today = datetime.date.today()

    for u in pwd.getpwall():
        if u.pw_name in IGNORE or u.pw_uid < 1000:
            continue
        if "nologin" in u.pw_shell or "false" in u.pw_shell:
            continue

        d = expire_date(u.pw_name)
        if d and d < today:
            subprocess.run(["passwd","-l",u.pw_name], check=False)
            subprocess.run(["bash","-lc",f"pkill -KILL -u {u.pw_name} || true"], check=False)

    time.sleep(60)
