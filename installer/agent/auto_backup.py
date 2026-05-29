#!/usr/bin/env python3

import os
import glob
import requests

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

# create backup
try:
    requests.post(
        "http://127.0.0.1:8000/backup/create2",
        headers={"Authorization":"Bearer local-cron"},
        timeout=120
    )
except Exception as e:
    print("backup create failed:",e)

# cleanup old backups
files=sorted(
    glob.glob("/opt/mrssh-backups/*.tar.gz"),
    reverse=True
)

for old in files[5:]:
    try:
        os.remove(old)
        print("deleted",old)
    except Exception as e:
        print("delete failed",old,e)
