"""
HealthSlip AI - MySQL Connection Test & Setup Tool
Run this script to verify your MySQL credentials and initialize the database schema:
    python test_mysql_connection.py
"""

import sys
import os
import urllib.parse
import pymysql
from dotenv import load_dotenv, set_key

load_dotenv()

def test_mysql():
    host = os.getenv("MYSQL_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("MYSQL_USER", "root")
    password = os.getenv("MYSQL_PASSWORD", "")
    db_name = os.getenv("MYSQL_DB", "healthslip_prod")

    print("=" * 60)
    print("HealthSlip AI - MySQL Connection Diagnostic")
    print("=" * 60)
    print(f"Target Server : {host}:{port}")
    print(f"Username      : {user}")
    print(f"Database      : {db_name}")
    print("-" * 60)

    try:
        conn = pymysql.connect(host=host, port=port, user=user, password=password)
        print("[OK] SUCCESS: Successfully authenticated with MySQL server!")
        
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            print(f"[OK] SUCCESS: Database `{db_name}` verified / created!")
        conn.close()

        # Update DATABASE_URL in .env
        encoded_pwd = urllib.parse.quote_plus(password)
        db_url = f"mysql+pymysql://{user}:{encoded_pwd}@{host}:{port}/{db_name}"
        set_key(".env", "DATABASE_URL", db_url)
        print(f"[OK] Updated .env DATABASE_URL to: {db_url}")
        print("\nHealthSlip AI is now fully connected to MySQL!")
        return True

    except pymysql.err.OperationalError as e:
        err_code, err_msg = e.args
        print(f"\n[FAIL] Connection Failed [Error {err_code}]: {err_msg}")
        if err_code == 1045:
            print("\nTIP: Access Denied means the password in `.env` is incorrect.")
            print("Please check the password you use when logging into MySQL Workbench.")
            print("You can update it directly in `.env`: MYSQL_PASSWORD=your_password")
        return False
    except Exception as e:
        print(f"\n[FAIL] Unexpected error: {e}")
        return False

if __name__ == "__main__":
    test_mysql()
