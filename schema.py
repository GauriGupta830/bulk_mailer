"""
AI Bulk Mailer Pro - Complete Database Schema
SQLite with full relational design
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "data/ai_bulk_mailer.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Initialize all database tables."""
    conn = get_connection()
    cur = conn.cursor()

    # ── USERS ──────────────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            email         TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            role          TEXT    NOT NULL DEFAULT 'user',  -- 'user' | 'admin'
            is_active     INTEGER NOT NULL DEFAULT 1,
            gmail_token   TEXT,          -- JSON OAuth token (encrypted)
            gmail_email   TEXT,          -- connected Gmail address
            created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            last_login    TEXT
        )
    """)

    # ── SESSIONS ───────────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token      TEXT    NOT NULL UNIQUE,
            created_at TEXT    NOT NULL DEFAULT (datetime('now')),
            expires_at TEXT    NOT NULL
        )
    """)

    # ── TEMPLATES ──────────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name       TEXT    NOT NULL,
            subject    TEXT    NOT NULL,
            body       TEXT    NOT NULL,
            created_at TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # ── CAMPAIGNS ──────────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            campaign_name   TEXT    NOT NULL,
            subject         TEXT    NOT NULL,
            template_body   TEXT    NOT NULL,
            status          TEXT    NOT NULL DEFAULT 'draft',
                -- draft | scheduled | running | paused | completed | cancelled | failed
            scheduled_at    TEXT,
            total_recipients INTEGER NOT NULL DEFAULT 0,
            sent_count      INTEGER NOT NULL DEFAULT 0,
            failed_count    INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            started_at      TEXT,
            completed_at    TEXT
        )
    """)

    # ── LEADS ──────────────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            name        TEXT,
            email       TEXT    NOT NULL,
            company     TEXT,
            phone       TEXT,
            extra_data  TEXT,   -- JSON for any additional columns
            lead_score  TEXT    DEFAULT 'cold',  -- hot | warm | cold
            status      TEXT    NOT NULL DEFAULT 'pending',
                -- pending | sent | failed | bounced
            sent_at     TEXT,
            error_msg   TEXT
        )
    """)

    # ── ANALYTICS ──────────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS analytics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            metric      TEXT    NOT NULL,  -- opened | clicked | bounced | unsubscribed
            lead_id     INTEGER REFERENCES leads(id),
            value       TEXT,
            tracked_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # ── AUDIT LOG ──────────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER REFERENCES users(id),
            action     TEXT    NOT NULL,
            detail     TEXT,
            ip_address TEXT,
            created_at TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # Indexes for performance
    cur.execute("CREATE INDEX IF NOT EXISTS idx_leads_campaign ON leads(campaign_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_user ON campaigns(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token)")

    conn.commit()
    conn.close()
    print("[DB] Schema initialized successfully.")


if __name__ == "__main__":
    init_db()
