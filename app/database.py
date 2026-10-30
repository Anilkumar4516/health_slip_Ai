import logging
import urllib.parse
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

logger = logging.getLogger("healthslip.database")
logging.basicConfig(level=logging.INFO)

Base = declarative_base()

ACTIVE_DB_TYPE = "Unknown"
DB_STATUS_DETAIL = ""

def init_engine():
    global ACTIVE_DB_TYPE, DB_STATUS_DETAIL
    
    # Try MySQL first
    encoded_pwd = urllib.parse.quote_plus(settings.MYSQL_PASSWORD)
    mysql_url = f"mysql+pymysql://{settings.MYSQL_USER}:{encoded_pwd}@{settings.MYSQL_HOST}:{settings.MYSQL_PORT}/{settings.MYSQL_DB}"
    try:
        # Check if database exists, create if not
        import pymysql
        conn = pymysql.connect(
            host=settings.MYSQL_HOST,
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
            port=settings.MYSQL_PORT
        )
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{settings.MYSQL_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        conn.close()

        engine = create_engine(
            mysql_url,
            pool_recycle=3600,
            pool_pre_ping=True
        )
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        ACTIVE_DB_TYPE = "MySQL"
        DB_STATUS_DETAIL = f"Connected to MySQL database '{settings.MYSQL_DB}' at {settings.MYSQL_HOST}:{settings.MYSQL_PORT}"
        logger.info(f"[OK] [Database] Successfully connected to MySQL ({settings.MYSQL_DB})")
        return engine
    except Exception as mysql_err:
        logger.warning(f"[WARN] [Database] MySQL connection failed ({mysql_err}).")
        
        # Enforce: No SQLite fallback in production mode!
        if settings.ENVIRONMENT.lower() == "production":
            error_msg = (
                f"[PRODUCTION FATAL] MySQL connection failed: {mysql_err}. "
                f"SQLite fallback is strictly forbidden in production mode."
            )
            logger.critical(error_msg)
            raise RuntimeError(error_msg)
        
        if settings.FALLBACK_TO_SQLITE:
            logger.info("[INFO] [Database] Falling back to SQLite database for seamless development & testing.")
            engine = create_engine(
                settings.SQLITE_DB_PATH,
                connect_args={"check_same_thread": False}
            )
            ACTIVE_DB_TYPE = "SQLite (Fallback)"
            DB_STATUS_DETAIL = f"Using SQLite fallback at {settings.SQLITE_DB_PATH} (MySQL connection error: {str(mysql_err)})"
            return engine
        else:
            raise mysql_err

engine = init_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_db_status():
    return {
        "active_db": ACTIVE_DB_TYPE,
        "detail": DB_STATUS_DETAIL,
        "configured_mysql_host": f"{settings.MYSQL_HOST}:{settings.MYSQL_PORT}",
        "configured_mysql_db": settings.MYSQL_DB
    }
