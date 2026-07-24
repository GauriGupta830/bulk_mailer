"""
Campaign Module - CRUD for campaigns, leads, templates
"""

import json
from datetime import datetime
from typing import Any

from database.schema import get_connection


# ── Campaigns ─────────────────────────────────────────────────────────────────

def create_campaign(user_id: int, name: str, subject: str, template_body: str,
                    total_recipients: int, scheduled_at: str | None = None) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO campaigns
           (user_id, campaign_name, subject, template_body, status,
            total_recipients, scheduled_at)
           VALUES (?,?,?,?,?,?,?)""",
        (user_id, name, subject, template_body,
         "scheduled" if scheduled_at else "draft",
         total_recipients, scheduled_at),
    )
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return cid


def get_campaigns(user_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM campaigns WHERE user_id=? ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_campaign(campaign_id: int, user_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM campaigns WHERE id=? AND user_id=?", (campaign_id, user_id)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_campaign_status(campaign_id: int, status: str):
    conn = get_connection()
    conn.execute("UPDATE campaigns SET status=? WHERE id=?", (status, campaign_id))
    conn.commit()
    conn.close()


def delete_campaign(campaign_id: int, user_id: int):
    conn = get_connection()
    conn.execute(
        "DELETE FROM campaigns WHERE id=? AND user_id=?", (campaign_id, user_id)
    )
    conn.commit()
    conn.close()


# ── Leads ─────────────────────────────────────────────────────────────────────

def insert_leads(campaign_id: int, leads: list[dict]):
    conn = get_connection()
    conn.executemany(
        """INSERT INTO leads (campaign_id, name, email, company, phone, extra_data, lead_score)
           VALUES (:campaign_id, :name, :email, :company, :phone, :extra_data, :lead_score)""",
        [{**l, "campaign_id": campaign_id} for l in leads],
    )
    conn.commit()
    conn.close()


def get_leads(campaign_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM leads WHERE campaign_id=? ORDER BY id", (campaign_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Templates ─────────────────────────────────────────────────────────────────

def save_template(user_id: int, name: str, subject: str, body: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO templates (user_id, name, subject, body) VALUES (?,?,?,?)",
        (user_id, name, subject, body),
    )
    conn.commit()
    tid = cur.lastrowid
    conn.close()
    return tid


def get_templates(user_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM templates WHERE user_id=? ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_template(template_id: int, user_id: int):
    conn = get_connection()
    conn.execute(
        "DELETE FROM templates WHERE id=? AND user_id=?", (template_id, user_id)
    )
    conn.commit()
    conn.close()


# ── Dashboard Stats ───────────────────────────────────────────────────────────

def get_dashboard_stats(user_id: int) -> dict[str, Any]:
    conn = get_connection()
    row = conn.execute(
        """SELECT
             COUNT(*) as total_campaigns,
             COALESCE(SUM(sent_count),0) as total_sent,
             COALESCE(SUM(failed_count),0) as total_failed
           FROM campaigns WHERE user_id=?""",
        (user_id,),
    ).fetchone()
    recent = conn.execute(
        """SELECT campaign_name, status, sent_count, failed_count, created_at
           FROM campaigns WHERE user_id=? ORDER BY created_at DESC LIMIT 5""",
        (user_id,),
    ).fetchall()
    conn.close()
    stats = dict(row)
    ts = stats["total_sent"]
    tf = stats["total_failed"]
    stats["success_rate"] = round(ts / (ts + tf) * 100, 1) if (ts + tf) > 0 else 0
    stats["recent_campaigns"] = [dict(r) for r in recent]
    return stats


# ── Reports ───────────────────────────────────────────────────────────────────

def get_campaign_report(campaign_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT name, email, company, lead_score, status, sent_at, error_msg
           FROM leads WHERE campaign_id=? ORDER BY id""",
        (campaign_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Admin ─────────────────────────────────────────────────────────────────────

def admin_get_all_users() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, email, role, is_active, created_at, last_login FROM users ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def admin_toggle_user(user_id: int, active: bool):
    conn = get_connection()
    conn.execute("UPDATE users SET is_active=? WHERE id=?", (int(active), user_id))
    conn.commit()
    conn.close()


def admin_get_all_campaigns() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT c.*, u.name as user_name, u.email as user_email
           FROM campaigns c JOIN users u ON u.id=c.user_id
           ORDER BY c.created_at DESC""",
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
