"""Password hashing, signed member tokens, and database-backed librarian sessions."""
import base64
import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from fastapi import Header, HTTPException, Request
from app.db import get_connection

TOKEN_SECRET = os.getenv("TOKEN_SECRET", "")


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200000)
    return "pbkdf2_sha256$200000$" + base64.urlsafe_b64encode(salt + digest).decode()


def verify_password(password, stored):
    try:
        algorithm, rounds, encoded = stored.split("$")
        raw = base64.urlsafe_b64decode(encoded.encode())
        expected = hashlib.pbkdf2_hmac("sha256", password.encode(), raw[:16], int(rounds))
        return algorithm == "pbkdf2_sha256" and hmac.compare_digest(expected, raw[16:])
    except (ValueError, TypeError):
        return False


def issue_member_token(member_id):
    if not TOKEN_SECRET:
        raise RuntimeError("TOKEN_SECRET must be configured")
    expiry = int(time.time()) + 3600
    body = str(member_id) + "." + str(expiry)
    signature = hmac.new(TOKEN_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode((body + "." + signature).encode()).decode().rstrip("=")


def require_member(authorization: str = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    try:
        raw = authorization[7:]
        raw += "=" * (-len(raw) % 4)
        member, expiry, signature = base64.urlsafe_b64decode(raw).decode().split(".")
        body = member + "." + expiry
        expected = hmac.new(TOKEN_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected) or int(expiry) < time.time():
            raise ValueError()
        return int(member)
    except (ValueError, TypeError, UnicodeDecodeError):
        raise HTTPException(401, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})


def require_librarian(request: Request):
    token = request.cookies.get("librarian_session")
    if not token:
        raise HTTPException(401, "Librarian session required")
    digest = hashlib.sha256(token.encode()).hexdigest()
    connection = get_connection()
    try:
        row = connection.execute("SELECT staff_id FROM librarian_sessions WHERE token_hash = ? AND expires_at > ?",
                                 (digest, datetime.now(timezone.utc).isoformat())).fetchone()
        if not row:
            raise HTTPException(401, "Invalid or expired librarian session")
        return row["staff_id"]
    finally:
        connection.close()


def verify_partner(api_key: str = Header(default=None, alias="X-API-Key"),
                   api_secret: str = Header(default=None, alias="X-API-Secret")):
    if not api_key or not api_secret:
        raise HTTPException(401, "Partner credentials required")
    connection = get_connection()
    try:
        row = connection.execute("SELECT api_key, secret_hash FROM partner_credentials WHERE name = ?", ("catalogue",)).fetchone()
        if not row or not hmac.compare_digest(api_key, row["api_key"]) or not verify_password(api_secret, row["secret_hash"]):
            raise HTTPException(401, "Invalid partner credentials")
    finally:
        connection.close()
