import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="allow")
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "HealthSlip AI")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() in ("true", "1")

    # Database
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "root")
    MYSQL_DB: str = os.getenv("MYSQL_DB", "healthslip_prod")
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
    )
    FALLBACK_TO_SQLITE: bool = os.getenv("FALLBACK_TO_SQLITE", "True").lower() in ("true", "1")
    SQLITE_DB_PATH: str = os.getenv("SQLITE_DB_PATH", "sqlite:///./healthslip.db")

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "healthslip_ai_cryptographic_hmac_secret_2026_secured")
    OTP_EXPIRY_MINUTES: int = int(os.getenv("OTP_EXPIRY_MINUTES", "5"))
    OTP_MAX_ATTEMPTS: int = int(os.getenv("OTP_MAX_ATTEMPTS", "3"))
    OTP_COOLDOWN_SECONDS: int = int(os.getenv("OTP_COOLDOWN_SECONDS", "60"))
    DEV_OTP_SANDBOX_MODE: bool = os.getenv("DEV_OTP_SANDBOX_MODE", "True").lower() in ("true", "1")

    # AI
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # End settings

settings = Settings()
