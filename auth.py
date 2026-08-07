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


# ── Profile ────────────────────────────────────────────────────────────────

def update_user_name(user_id: int, name: str) -> bool:
    name = name.strip()
    if not name:
        return False
    conn = get_connection()
    try:
        conn.execute("UPDATE users SET name=? WHERE id=?", (name, user_id))
        conn.commit()
        return True
    finally:
        conn.close()


# ── Multiple Gmail Accounts ──────────────────────────────────────────────────

def _ensure_gmail_accounts_table():
    conn = get_connection()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS gmail_accounts (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER NOT NULL,
                 email TEXT NOT NULL,
                 token_json TEXT NOT NULL,
                 is_active INTEGER DEFAULT 0,
                 created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                 UNIQUE(user_id, email)
               )"""
        )
        conn.commit()
    finally:
        conn.close()


def add_or_update_gmail_account(user_id: int, email: str, token_json: str):
    """Link a Gmail account (or refresh its token if already linked).
    New accounts are NOT auto-activated if the user already has one active —
    they land in the list so the user can switch to them explicitly.
    The very first account linked for a user becomes active automatically.
    """
    _ensure_gmail_accounts_table()
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM gmail_accounts WHERE user_id=? AND email=?", (user_id, email)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE gmail_accounts SET token_json=? WHERE id=?", (token_json, existing["id"])
            )
            account_id = existing["id"]
        else:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO gmail_accounts (user_id, email, token_json, is_active) VALUES (?,?,?,0)",
                (user_id, email, token_json),
            )
            account_id = cur.lastrowid

        any_active = conn.execute(
            "SELECT id FROM gmail_accounts WHERE user_id=? AND is_active=1", (user_id,)
        ).fetchone()
        conn.commit()
    finally:
        conn.close()

    if not any_active:
        activate_gmail_account(user_id, account_id)

    return account_id


def list_gmail_accounts(user_id: int) -> list[dict]:
    _ensure_gmail_accounts_table()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, email, is_active FROM gmail_accounts WHERE user_id=? ORDER BY created_at",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def activate_gmail_account(user_id: int, account_id: int) -> bool:
    _ensure_gmail_accounts_table()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM gmail_accounts WHERE id=? AND user_id=?", (account_id, user_id)
        ).fetchone()
        if not row:
            return False
        conn.execute("UPDATE gmail_accounts SET is_active=0 WHERE user_id=?", (user_id,))
        conn.execute("UPDATE gmail_accounts SET is_active=1 WHERE id=?", (account_id,))
        # Mirror into users table so the existing send_campaign()/get_gmail_token() flow keeps working unchanged
        conn.execute(
            "UPDATE users SET gmail_token=?, gmail_email=? WHERE id=?",
            (row["token_json"], row["email"], user_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def remove_gmail_account(user_id: int, account_id: int) -> bool:
    _ensure_gmail_accounts_table()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM gmail_accounts WHERE id=? AND user_id=?", (account_id, user_id)
        ).fetchone()
        if not row:
            return False
        was_active = bool(row["is_active"])
        conn.execute("DELETE FROM gmail_accounts WHERE id=?", (account_id,))
        conn.commit()
    finally:
        conn.close()

    if was_active:
        remaining = list_gmail_accounts(user_id)
        if remaining:
            activate_gmail_account(user_id, remaining[0]["id"])
        else:
            save_gmail_token(user_id, "", "")
    return True


# ── Unsubscribe / Suppression List ──────────────────────────────────────────

def _ensure_unsubscribes_table():
    conn = get_connection()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS unsubscribes (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER NOT NULL,
                 email TEXT NOT NULL,
                 created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                 UNIQUE(user_id, email)
               )"""
        )
        conn.commit()
    finally:
        conn.close()


def generate_unsubscribe_token(user_id: int, email: str) -> str:
    msg = f"{user_id}:{email.lower().strip()}".encode()
    return hmac.new(SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()[:24]


def verify_unsubscribe_token(user_id: int, email: str, token: str) -> bool:
    expected = generate_unsubscribe_token(user_id, email)
    return hmac.compare_digest(expected, token or "")


def add_unsubscribe(user_id: int, email: str):
    _ensure_unsubscribes_table()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO unsubscribes (user_id, email) VALUES (?,?)",
            (user_id, email.lower().strip()),
        )
        conn.commit()
    finally:
        conn.close()


def is_unsubscribed(user_id: int, email: str) -> bool:
    _ensure_unsubscribes_table()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM unsubscribes WHERE user_id=? AND email=?",
            (user_id, email.lower().strip()),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def list_unsubscribes(user_id: int) -> list[dict]:
    _ensure_unsubscribes_table()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT email, created_at FROM unsubscribes WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
