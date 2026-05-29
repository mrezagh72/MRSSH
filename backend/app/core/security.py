from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from fastapi import HTTPException, Header
from .config import settings

ALGORITHM = "HS256"

def create_token(username: str, role: str = "super_admin") -> str:
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=12)
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return {"username": payload["sub"], "role": payload.get("role", "viewer")}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
