"""Small SQLite data layer. Every request owns and closes its connection."""
import os
import hashlib
import hmac
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "database" / "schema.sql"
SEED = ROOT / "database" / "seed.sql"


def get_connection():
    path = os.getenv("DATABASE_PATH", str(ROOT / "library.db"))
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    from app.auth import hash_password
    if not os.getenv("TOKEN_SECRET"):
        raise RuntimeError("Set TOKEN_SECRET before starting the library API")
    if not os.getenv("PARTNER_API_KEY") or not os.getenv("PARTNER_API_SECRET"):
        raise RuntimeError("Set PARTNER_API_KEY and PARTNER_API_SECRET before starting the library API")
    connection = get_connection()
    try:
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))
        # Seed rows are inserted by stable natural keys, so startup is repeatable.
        connection.executescript(SEED.read_text(encoding="utf-8"))
        sample_logins = (("SELECT password_hash FROM members WHERE email = ?", "UPDATE members SET password_hash = ? WHERE email = ?", "aman@example.com"),
                         ("SELECT password_hash FROM members WHERE email = ?", "UPDATE members SET password_hash = ? WHERE email = ?", "priya@example.com"),
                         ("SELECT password_hash FROM members WHERE email = ?", "UPDATE members SET password_hash = ? WHERE email = ?", "rahul@example.com"),
                         ("SELECT password_hash FROM staff WHERE email = ?", "UPDATE staff SET password_hash = ? WHERE email = ?", "librarian1@example.com"),
                         ("SELECT password_hash FROM staff WHERE email = ?", "UPDATE staff SET password_hash = ? WHERE email = ?", "librarian2@example.com"),
                         ("SELECT password_hash FROM staff WHERE email = ?", "UPDATE staff SET password_hash = ? WHERE email = ?", "librarian3@example.com"))
        for select_sql, update_sql, email in sample_logins:
            row = connection.execute(select_sql, (email,)).fetchone()
            if row and not row[0].startswith("pbkdf2_sha256$"):
                connection.execute(update_sql, (hash_password("password123"), email))
        partner_key = os.getenv("PARTNER_API_KEY")
        partner_secret = os.getenv("PARTNER_API_SECRET")
        row = connection.execute("SELECT partner_id FROM partner_credentials WHERE name = ?", ("catalogue",)).fetchone()
        if row is None:
            connection.execute("INSERT INTO partner_credentials(name,api_key,secret_hash) VALUES(?,?,?)",
                               ("catalogue", partner_key, hash_password(partner_secret)))
        elif os.getenv("PARTNER_API_KEY") or os.getenv("PARTNER_API_SECRET"):
            connection.execute("UPDATE partner_credentials SET api_key=?,secret_hash=? WHERE name=?",
                               (partner_key, hash_password(partner_secret), "catalogue"))
        connection.commit()
    finally:
        connection.close()
