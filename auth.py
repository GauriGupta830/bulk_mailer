"""
Authentication Module
Handles signup, login, logout, session tokens
"""

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timedelta

from database.schema import get_connection

SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production-32chars!!")
SESSION_HOURS = 72


# ── Password Hashing ──────────────────────────────────────────────────────────

def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return dk.hex(), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    dk, _ = _hash_password(password, salt)
    return hmac.compare_digest(dk, stored_hash)


# ── User CRUD ─────────────────────────────────────────────────────────────────

def create_user(name: str, email: str, password: str) -> dict | None:
    """Returns user dict on success, None if email already exists."""
    pw_hash, salt = _hash_password(password)
    stored = f"{salt}:{pw_hash}"   # store as  salt:hash
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?,?,?)",
            (name.strip(), email.lower().strip(), stored),
        )
        conn.commit()
        user_id = cur.lastrowid
        return {"id": user_id, "name": name, "email": email, "role": "user"}
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def authenticate_user(email: str, password: str) -> dict | None:
    """Returns user dict if credentials valid, else None."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email=? AND is_active=1",
            (email.lower().strip(),),
        ).fetchone()
        if not row:
            return None
        stored: str = row["password_hash"]
        salt, pw_hash = stored.split(":", 1)
        if not verify_password(password, pw_hash, salt):
            return None
        conn.execute(
            "UPDATE users SET last_login=? WHERE id=?",
            (datetime.utcnow().isoformat(), row["id"]),
        )
        conn.commit()
        return dict(row)
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ── Session Management ────────────────────────────────────────────────────────

def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(48)
    expires = (datetime.utcnow() + timedelta(hours=SESSION_HOURS)).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO sessions (user_id, token, expires_at) VALUES (?,?,?)",
            (user_id, token, expires),
        )
        conn.commit()
        return token
    finally:
        conn.close()


def validate_session(token: str) -> dict | None:
    """Returns user dict if session is valid and not expired."""
    if not token:
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT s.user_id, s.expires_at, u.name, u.email, u.role, u.is_active
               FROM sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token=?""",
            (token,),
        ).fetchone()
        if not row:
            return None
        if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            conn.commit()
            return None
        if not row["is_active"]:
            return None
        return dict(row)
    finally:
        conn.close()


def delete_session(token: str):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))
        conn.commit()
    finally:
        conn.close()


# ── Gmail OAuth token storage ──────────────────────────────────────────────────

def save_gmail_token(user_id: int, token_json: str, gmail_email: str):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET gmail_token=?, gmail_email=? WHERE id=?",
            (token_json, gmail_email, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_gmail_token(user_id: int) -> tuple[str | None, str | None]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT gmail_token, gmail_email FROM users WHERE id=?", (user_id,)
        ).fetchone()
        if row:
            return row["gmail_token"], row["gmail_email"]
        return None, None
    finally:
        conn.close()
