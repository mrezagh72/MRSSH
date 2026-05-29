from datetime import datetime, timedelta

USERS = [
    {"username":"amir_admin","owner":"root","status":"active","traffic":"1.45 TB / ∞","usedPercent":34,"expire":"2026-06-20","online":True,"ip":"185.123.45.67","connections":"1/2"},
    {"username":"sina_style","owner":"reseller-a","status":"active","traffic":"1.23 TB / 2 TB","usedPercent":61,"expire":"2026-05-25","online":True,"ip":"37.152.12.89","connections":"2/3"},
    {"username":"hossein_2024","owner":"reseller-b","status":"active","traffic":"980 GB / 1 TB","usedPercent":98,"expire":"2026-05-22","online":True,"ip":"5.63.12.34","connections":"1/1"},
    {"username":"ali_ax","owner":"root","status":"expired","traffic":"512 GB / 500 GB","usedPercent":100,"expire":"2026-05-18","online":False,"ip":"185.55.12.98","connections":"0/1"},
    {"username":"mmd_service","owner":"reseller-a","status":"active","traffic":"760 GB / ∞","usedPercent":22,"expire":"2026-07-20","online":False,"ip":"91.98.76.54","connections":"0/5"},
]

def dashboard():
    return {
        "stats": {"totalUsers":1425,"onlineUsers":256,"traffic":"92.4 TB","servers":3,"expiring":48},
        "trafficSeries": [8.4,10.6,11.5,13.7,12.8,18.7,13.4,17.1,19.8],
        "servers": [
            {"name":"IR-Tehran-01","ip":"185.123.45.67","status":"Online","uptime":"15d 8h"},
            {"name":"IR-Tehran-02","ip":"91.98.76.54","status":"Online","uptime":"22d 14h"},
            {"name":"DE-Frankfurt-01","ip":"45.87.12.34","status":"Online","uptime":"7d 3h"},
        ],
        "users": USERS,
        "activities": [
            {"text":"User amir_admin logged in","time":"2 min ago"},
            {"text":"User sina_style traffic limit updated","time":"5 min ago"},
            {"text":"New user created: mmd_service","time":"10 min ago"},
            {"text":"User ali_ax disconnected","time":"15 min ago"},
        ]
    }
