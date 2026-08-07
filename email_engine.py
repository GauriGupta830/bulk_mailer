"""
Email Sending Engine
Gmail API + OAuth 2.0, queue-based, retry, rate limiting
"""

import base64
import json
import os
import re
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from backend.auth.auth import (
    get_gmail_token, save_gmail_token, add_or_update_gmail_account,
    generate_unsubscribe_token, is_unsubscribed,
)
from database.schema import get_connection

# ── OAuth Config ──────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]
REDIRECT_URI = os.environ.get(
    "OAUTH_REDIRECT_URI", "http://localhost:8000/oauth_callback"
)

def _base_url_from_redirect(redirect_uri: str) -> str:
    from urllib.parse import urlparse
    parsed = urlparse(redirect_uri)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return "http://localhost:8000"

BASE_URL = os.environ.get("PUBLIC_BASE_URL", _base_url_from_redirect(REDIRECT_URI))
CLIENT_SECRETS_FILE = os.environ.get("GOOGLE_CLIENT_SECRETS", "client_secrets.json")
if not os.path.isabs(CLIENT_SECRETS_FILE):
    _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    CLIENT_SECRETS_FILE = os.path.join(_PROJECT_ROOT, CLIENT_SECRETS_FILE)

# Rate limiting: Gmail free = 100 emails/day, 1/sec recommended
SEND_DELAY_SECONDS = float(os.environ.get("SEND_DELAY_SECONDS", "1.5"))
MAX_RETRIES = 3


# ── OAuth Flow ────────────────────────────────────────────────────────────────

def get_auth_url(state: str) -> str:
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI
    )
    flow.state = state
    auth_url, _ = flow.authorization_url(
        access_type="offline", prompt="consent", state=state
    )
    return auth_url


def exchange_code_for_token(code: str, state: str, user_id: int) -> str:
    """Exchange OAuth code → credentials, save to DB, return gmail address."""
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
        state=state,
    )
    flow.fetch_token(code=code)
    creds = flow.credentials

    # Get user email
    service = build("oauth2", "v2", credentials=creds)
    user_info = service.userinfo().get().execute()
    gmail_email = user_info.get("email", "")

    token_json = creds.to_json()
    add_or_update_gmail_account(user_id, gmail_email, token_json)
    return gmail_email


def _get_credentials(user_id: int) -> Credentials | None:
    token_json, _ = get_gmail_token(user_id)
    if not token_json:
        return None
    creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_gmail_token(user_id, creds.to_json(), _)
    return creds if creds.valid else None


def _build_message(sender: str, to: str, subject: str, body: str, unsubscribe_url: str = "") -> dict:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    if unsubscribe_url:
        msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"

    # Detect any HTML markup (not just <html>/<br> — AI-generated emails commonly
    # use <div>, <table>, <p>, <a>, <strong>, <img>, etc. without a full <html> wrapper)
    is_html = bool(re.search(r"<\s*[a-zA-Z][^>]*>", body))

    if unsubscribe_url:
        if is_html:
            body += (
                f'<div style="margin-top:24px;padding-top:14px;border-top:1px solid #e5e5e5;'
                f'font-family:Arial,sans-serif;font-size:11px;color:#9aa0a6;text-align:center">'
                f'You are receiving this email because you were added as a lead. '
                f'<a href="{unsubscribe_url}" style="color:#9aa0a6;text-decoration:underline">Unsubscribe</a>'
                f'</div>'
            )
        else:
            body += f"\n\n---\nDon't want these emails? Unsubscribe: {unsubscribe_url}"

    if is_html:
        msg.attach(MIMEText(body, "html"))
    else:
        msg.attach(MIMEText(body, "plain"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {"raw": raw}


# ── Sending Engine ─────────────────────────────────────────────────────────────

def send_campaign(campaign_id: int, user_id: int, progress_callback=None):
    """
    Send all pending leads for a campaign.
    progress_callback(sent, failed, total, current_email) for live UI updates.
    """
    try:
        creds = _get_credentials(user_id)
        if not creds:
            raise RuntimeError("Gmail not connected. Please connect your Gmail account.")

        _, gmail_email = get_gmail_token(user_id)
        service = build("gmail", "v1", credentials=creds)

        conn = get_connection()
        campaign = conn.execute(
            "SELECT * FROM campaigns WHERE id=? AND user_id=?", (campaign_id, user_id)
        ).fetchone()

        if not campaign:
            conn.close()
            raise ValueError("Campaign not found.")

        leads = conn.execute(
            "SELECT * FROM leads WHERE campaign_id=? AND status='pending'", (campaign_id,)
        ).fetchall()
        conn.close()
    except Exception as e:
        # Failed before we even started sending — don't leave the campaign stuck on "running"
        try:
            _update_campaign_status(campaign_id, "failed", completed_at=True)
        except Exception:
            pass
        raise

    total = len(leads)
    sent = 0
    failed = 0

    # Mark campaign as running
    _update_campaign_status(campaign_id, "running", started_at=True)

    from backend.utils.excel_processor import personalize_email
    from urllib.parse import quote

    try:
        for lead in leads:
            lead = dict(lead)

            try:
                if is_unsubscribed(user_id, lead["email"]):
                    _update_lead(lead["id"], "skipped_unsubscribed", "Recipient had previously unsubscribed.")
                    _update_campaign_counts(campaign_id, sent, failed)
                    if progress_callback:
                        progress_callback(sent, failed, total, lead["email"] + " (skipped — unsubscribed)")
                    continue

                body = personalize_email(campaign["template_body"], lead)
                subject = personalize_email(campaign["subject"], lead)

                try:
                    token = generate_unsubscribe_token(user_id, lead["email"])
                    unsubscribe_url = f"{BASE_URL}/unsubscribe?u={user_id}&e={quote(lead['email'])}&t={token}"
                except Exception:
                    unsubscribe_url = ""  # fall back to sending without an unsubscribe link rather than crashing

                msg = _build_message(gmail_email, lead["email"], subject, body, unsubscribe_url)

                success = False
                error_msg = ""
                for attempt in range(MAX_RETRIES):
                    try:
                        service.users().messages().send(userId="me", body=msg).execute()
                        success = True
                        break
                    except HttpError as e:
                        error_msg = str(e)
                        if e.resp.status in (429, 500, 503):
                            time.sleep(2 ** attempt)   # exponential back-off
                        else:
                            break  # permanent error (bad address etc.)
                    except Exception as e:
                        error_msg = str(e)
                        break

                if success:
                    sent += 1
                    _update_lead(lead["id"], "sent", None)
                else:
                    failed += 1
                    _update_lead(lead["id"], "failed", error_msg)

                _update_campaign_counts(campaign_id, sent, failed)

                if progress_callback:
                    progress_callback(sent, failed, total, lead["email"])

            except Exception as e:
                # Never let one bad lead crash the whole campaign — mark it failed and move on
                failed += 1
                try:
                    _update_lead(lead["id"], "failed", f"Unexpected error: {e}")
                    _update_campaign_counts(campaign_id, sent, failed)
                except Exception:
                    pass

            time.sleep(SEND_DELAY_SECONDS)
    finally:
        # Guarantee the campaign never stays stuck on "running" even if something above crashed
        _update_campaign_status(campaign_id, "completed", completed_at=True)


# ── Notifications (Inbox Digest) ───────────────────────────────────────────

def get_recent_notifications(user_id: int, max_results: int = 20) -> list[dict]:
    """
    Fetch recent inbox messages and classify each as:
      - 'reply'        → subject looks like a reply (Re: ...)
      - 'unsubscribe'  → subject/snippet mentions unsubscribing
      - 'message'      → anything else
    Returns newest first.
    """
    creds = _get_credentials(user_id)
    if not creds:
        return []

    service = build("gmail", "v1", credentials=creds)
    try:
        results = service.users().messages().list(
            userId="me", labelIds=["INBOX"], maxResults=max_results
        ).execute()
    except HttpError:
        return []

    notifications = []
    for msg_ref in results.get("messages", []):
        try:
            msg = service.users().messages().get(
                userId="me", id=msg_ref["id"],
                format="metadata", metadataHeaders=["From", "Subject", "Date"],
            ).execute()
        except HttpError:
            continue

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        subject = headers.get("Subject", "(no subject)")
        sender = headers.get("From", "Unknown sender")
        date = headers.get("Date", "")
        snippet = msg.get("snippet", "")

        text = (subject + " " + snippet).lower()
        if "unsubscribe" in text:
            ntype = "unsubscribe"
        elif subject.strip().lower().startswith(("re:", "re :")):
            ntype = "reply"
        else:
            ntype = "message"

        notifications.append({
            "id": msg_ref["id"],
            "from": sender,
            "subject": subject,
            "snippet": snippet,
            "date": date,
            "type": ntype,
            "unread": "UNREAD" in msg.get("labelIds", []),
        })

    return notifications


# ── DB Helpers ────────────────────────────────────────────────────────────────

def _update_lead(lead_id: int, status: str, error_msg: str | None):
    from datetime import datetime
    conn = get_connection()
    conn.execute(
        "UPDATE leads SET status=?, sent_at=?, error_msg=? WHERE id=?",
        (status, datetime.utcnow().isoformat(), error_msg, lead_id),
    )
    conn.commit()
    conn.close()


def _update_campaign_counts(campaign_id: int, sent: int, failed: int):
    conn = get_connection()
    conn.execute(
        "UPDATE campaigns SET sent_count=?, failed_count=? WHERE id=?",
        (sent, failed, campaign_id),
    )
    conn.commit()
    conn.close()


def _update_campaign_status(campaign_id: int, status: str,
                             started_at=False, completed_at=False):
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    if started_at:
        conn.execute(
            "UPDATE campaigns SET status=?, started_at=? WHERE id=?",
            (status, now, campaign_id),
        )
    elif completed_at:
        conn.execute(
            "UPDATE campaigns SET status=?, completed_at=? WHERE id=?",
            (status, now, campaign_id),
        )
    else:
        conn.execute("UPDATE campaigns SET status=? WHERE id=?", (status, campaign_id))
    conn.commit()
    conn.close()
