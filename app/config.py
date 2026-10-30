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
    HMAC_KEY_VERSION: str = os.getenv("HMAC_KEY_VERSION", "v1")
    OTP_EXPIRY_MINUTES: int = int(os.getenv("OTP_EXPIRY_MINUTES", "5"))
    OTP_MAX_ATTEMPTS: int = int(os.getenv("OTP_MAX_ATTEMPTS", "3"))
    OTP_COOLDOWN_SECONDS: int = int(os.getenv("OTP_COOLDOWN_SECONDS", "60"))
    DEV_OTP_SANDBOX_MODE: bool = os.getenv("DEV_OTP_SANDBOX_MODE", "True").lower() in ("true", "1")
    RATE_LIMIT_IP_MAX_PER_HOUR: int = int(os.getenv("RATE_LIMIT_IP_MAX_PER_HOUR", "15"))
    RATE_LIMIT_PHONE_MAX_PER_HOUR: int = int(os.getenv("RATE_LIMIT_PHONE_MAX_PER_HOUR", "5"))

    # SMS Providers (MSG91 / Fast2SMS / Console Mock)
    SMS_PROVIDER: str = os.getenv("SMS_PROVIDER", "console")
    FAST2SMS_API_KEY: str = os.getenv("FAST2SMS_API_KEY", "")
    FAST2SMS_SENDER_ID: str = os.getenv("FAST2SMS_SENDER_ID", "")
    FAST2SMS_DLT_TE_ID: str = os.getenv("FAST2SMS_DLT_TE_ID", "")
    MSG91_AUTH_KEY: str = os.getenv("MSG91_AUTH_KEY", "")
    MSG91_SENDER_ID: str = os.getenv("MSG91_SENDER_ID", "HLTSLP")
    MSG91_DLT_TE_ID: str = os.getenv("MSG91_DLT_TE_ID", "")

    # Redis Scaling
    REDIS_ENABLED: bool = os.getenv("REDIS_ENABLED", "False").lower() in ("true", "1")
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_URL: str = os.getenv("REDIS_URL", "")

    # AI & Heuristics
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    ENABLE_EXTERNAL_AI: bool = os.getenv("ENABLE_EXTERNAL_AI", "False").lower() in ("true", "1")

    # DPDP Act & Encryption
    DATA_ENCRYPTION_KEY: str = os.getenv("DATA_ENCRYPTION_KEY", "")
    CORS_ALLOWED_ORIGINS: str = os.getenv("CORS_ALLOWED_ORIGINS", "*")

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # End settings

settings = Settings()
