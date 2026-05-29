from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SECRET_KEY: str = "change-this-secret"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123456"

settings = Settings()
