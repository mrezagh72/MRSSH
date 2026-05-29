import json, os, time, subprocess, signal

META_FILE = "/opt/mrssh-agent/users_meta.json"

def load_meta():
    if not os.path.exists(META_FILE):
        return {}
    try:
        with open(META_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def ssh_pids(username):
    cmd = ["bash","-lc",f"ps -eo pid,user,args | grep 'sshd:' | grep '{username}@' | grep -v grep"]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
    pids = []
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) >= 2:
            try:
                pids.append(int(parts[0]))
            except:
                pass
    return sorted(set(pids))

while True:
    meta = load_meta()
    for username, cfg in meta.items():
        max_online = int(cfg.get("maxOnline", 1) or 1)
        pids = ssh_pids(username)

        if len(pids) > max_online:
            extra = pids[max_online:]
            for pid in extra:
                try:
                    os.kill(pid, signal.SIGTERM)
                except:
                    pass

    time.sleep(10)
