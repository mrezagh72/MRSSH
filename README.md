# MRSSH v4 Monster UI

Premium dark SSH panel UI + FastAPI mock backend.

## Install

```bash
cp .env.example .env
docker compose up -d --build --force-recreate
```

Open:
- Panel: http://SERVER_IP
- Frontend direct: http://SERVER_IP:3000
- API docs: http://SERVER_IP:8000/docs

Default login:
- admin / admin123456

Note: SSH engine is mocked. Real Linux user management should be added in backend/app/services/ssh_service.py.
