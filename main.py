"""
MailFlow Pro — FastAPI Backend
Wraps the existing AI Bulk Mailer Pro logic (auth, campaigns, excel processing,
AI features, reports, Gmail sending) behind a REST API so the new static
index.html dashboard can talk to it via fetch().

Run:
    uvicorn main:app --reload --port 8000
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, Response, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import io

from database.schema import init_db
from backend.auth.auth import (
    authenticate_user, create_user, create_session,
    validate_session, delete_session, get_gmail_token, get_user_by_id,
)
from backend.campaigns.campaigns import (
    create_campaign, get_campaigns, get_campaign,
    update_campaign_status, delete_campaign,
    insert_leads, get_leads,
    save_template, get_templates, delete_template,
    get_dashboard_stats, get_campaign_report,
)
from backend.utils.excel_processor import process_file, df_to_leads
from backend.ai.ai_features import generate_email, generate_subjects
from backend.reports.reports import export_report_csv, export_report_excel
from services.email_engine import get_auth_url, exchange_code_for_token, send_campaign

init_db()

app = FastAPI(title="MailFlow Pro API")

COOKIE_NAME = "session_token"


# ── Auth helper ────────────────────────────────────────────────────────────

def _current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    user = validate_session(token) if token else None
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ── AUTH ROUTES ──────────────────────────────────────────────────────────────

@app.post("/api/auth/signup")
async def api_signup(response: Response, name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")
    user = create_user(name, email, password)
    if not user:
        raise HTTPException(400, "An account with this email already exists.")
    token = create_session(user["id"])
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", max_age=72 * 3600)
    return {"name": user["name"], "email": user["email"], "role": user["role"]}


@app.post("/api/auth/login")
async def api_login(response: Response, email: str = Form(...), password: str = Form(...)):
    user = authenticate_user(email, password)
    if not user:
        raise HTTPException(401, "Invalid email or password.")
    token = create_session(user["id"])
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", max_age=72 * 3600)
    return {"name": user["name"], "email": user["email"], "role": user["role"]}


@app.post("/api/auth/logout")
async def api_logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        delete_session(token)
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@app.get("/api/auth/me")
async def api_me(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    user = validate_session(token) if token else None
    if not user:
        return JSONResponse({"authenticated": False}, status_code=200)
    return {"authenticated": True, "name": user["name"], "email": user["email"], "role": user["role"]}


# ── Gmail OAuth ────────────────────────────────────────────────────────────

@app.get("/api/settings/gmail-status")
async def gmail_status(request: Request):
    user = _current_user(request)
    _, gmail_email = get_gmail_token(user["user_id"])
    return {"connected": bool(gmail_email), "email": gmail_email}


@app.post("/api/settings/gmail-disconnect")
async def gmail_disconnect(request: Request):
    from backend.auth.auth import save_gmail_token
    user = _current_user(request)
    save_gmail_token(user["user_id"], "", "")
    return {"ok": True}


@app.get("/api/auth/gmail/connect")
async def gmail_connect(request: Request):
    user = _current_user(request)
    if not os.path.exists(os.environ.get("GOOGLE_CLIENT_SECRETS", "client_secrets.json")):
        raise HTTPException(400, "client_secrets.json not configured on server.")
    state = f"uid_{user['user_id']}"
    url = get_auth_url(state)
    return RedirectResponse(url)


@app.get("/oauth_callback")
async def oauth_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None):
    if not code or not state or not state.startswith("uid_"):
        return RedirectResponse("/?gmail=error")
    user_id = int(state.replace("uid_", ""))
    try:
        exchange_code_for_token(code, state, user_id)
        return RedirectResponse("/?gmail=connected")
    except Exception as e:
        return RedirectResponse(f"/?gmail=error&msg={e}")


# ── DASHBOARD ────────────────────────────────────────────────────────────────

@app.get("/api/dashboard/stats")
async def api_dashboard_stats(request: Request):
    user = _current_user(request)
    stats = get_dashboard_stats(user["user_id"])
    _, gmail_email = get_gmail_token(user["user_id"])
    stats["gmail_connected"] = bool(gmail_email)
    stats["gmail_email"] = gmail_email
    return stats


# ── CAMPAIGNS ────────────────────────────────────────────────────────────────

@app.get("/api/campaigns")
async def api_list_campaigns(request: Request):
    user = _current_user(request)
    return get_campaigns(user["user_id"])


@app.get("/api/campaigns/{campaign_id}")
async def api_get_campaign(campaign_id: int, request: Request):
    user = _current_user(request)
    c = get_campaign(campaign_id, user["user_id"])
    if not c:
        raise HTTPException(404, "Campaign not found")
    c["leads"] = get_leads(campaign_id)
    return c


@app.delete("/api/campaigns/{campaign_id}")
async def api_delete_campaign(campaign_id: int, request: Request):
    user = _current_user(request)
    delete_campaign(campaign_id, user["user_id"])
    return {"ok": True}


@app.post("/api/leads/preview")
async def api_leads_preview(file: UploadFile = File(...)):
    content = await file.read()
    result = process_file(content, file.filename)
    if result.get("errors"):
        raise HTTPException(400, "; ".join(result["errors"]))
    df = result["df"]
    return {
        "total": result["total"],
        "duplicates_removed": result["duplicates_removed"],
        "invalid_emails": result["invalid_emails"],
        "columns": result["columns"],
        "preview": df.head(5).to_dict(orient="records"),
    }


@app.post("/api/campaigns")
async def api_create_campaign(
    request: Request,
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    file: UploadFile = File(...),
    launch_now: bool = Form(True),
):
    user = _current_user(request)
    content = await file.read()
    result = process_file(content, file.filename)
    if result.get("errors"):
        raise HTTPException(400, "; ".join(result["errors"]))

    df = result["df"]
    leads = df_to_leads(df)

    campaign_id = create_campaign(
        user_id=user["user_id"],
        name=name,
        subject=subject,
        template_body=body,
        total_recipients=len(leads),
    )
    insert_leads(campaign_id, leads)

    if launch_now:
        _, gmail_email = get_gmail_token(user["user_id"])
        if not gmail_email:
            raise HTTPException(400, "Gmail not connected. Please connect Gmail in Settings first.")
        background_tasks.add_task(send_campaign, campaign_id, user["user_id"])
        update_campaign_status(campaign_id, "running")

    return {"campaign_id": campaign_id, "total_recipients": len(leads)}


@app.post("/api/campaigns/{campaign_id}/launch")
async def api_launch_campaign(campaign_id: int, request: Request, background_tasks: BackgroundTasks):
    user = _current_user(request)
    c = get_campaign(campaign_id, user["user_id"])
    if not c:
        raise HTTPException(404, "Campaign not found")
    _, gmail_email = get_gmail_token(user["user_id"])
    if not gmail_email:
        raise HTTPException(400, "Gmail not connected. Please connect Gmail in Settings first.")
    background_tasks.add_task(send_campaign, campaign_id, user["user_id"])
    update_campaign_status(campaign_id, "running")
    return {"ok": True}


# ── TEMPLATES ────────────────────────────────────────────────────────────────

@app.get("/api/templates")
async def api_list_templates(request: Request):
    user = _current_user(request)
    return get_templates(user["user_id"])


@app.post("/api/templates")
async def api_create_template(request: Request, name: str = Form(...), subject: str = Form(...), body: str = Form(...)):
    user = _current_user(request)
    tid = save_template(user["user_id"], name, subject, body)
    return {"id": tid}


@app.delete("/api/templates/{template_id}")
async def api_delete_template(template_id: int, request: Request):
    user = _current_user(request)
    delete_template(template_id, user["user_id"])
    return {"ok": True}


# ── AI TOOLS ─────────────────────────────────────────────────────────────────

@app.post("/api/ai/generate-email")
async def api_generate_email(request: Request, prompt: str = Form(...), tone: str = Form("professional")):
    _current_user(request)
    try:
        return generate_email(prompt, tone)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/ai/generate-subjects")
async def api_generate_subjects(request: Request, context: str = Form(...), count: int = Form(10)):
    _current_user(request)
    try:
        return {"subjects": generate_subjects(context, count)}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── REPORTS ──────────────────────────────────────────────────────────────────

@app.get("/api/reports/{campaign_id}")
async def api_campaign_report(campaign_id: int, request: Request):
    user = _current_user(request)
    c = get_campaign(campaign_id, user["user_id"])
    if not c:
        raise HTTPException(404, "Campaign not found")
    leads = get_campaign_report(campaign_id)
    return {"campaign": c, "leads": leads}


@app.get("/api/reports/{campaign_id}/export/csv")
async def api_export_csv(campaign_id: int, request: Request):
    user = _current_user(request)
    c = get_campaign(campaign_id, user["user_id"])
    if not c:
        raise HTTPException(404, "Campaign not found")
    leads = get_campaign_report(campaign_id)
    data = export_report_csv(leads)
    return StreamingResponse(
        io.BytesIO(data), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={c['campaign_name']}_report.csv"},
    )


@app.get("/api/reports/{campaign_id}/export/xlsx")
async def api_export_xlsx(campaign_id: int, request: Request):
    user = _current_user(request)
    c = get_campaign(campaign_id, user["user_id"])
    if not c:
        raise HTTPException(404, "Campaign not found")
    leads = get_campaign_report(campaign_id)
    data = export_report_excel(leads, c["campaign_name"])
    return StreamingResponse(
        io.BytesIO(data), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={c['campaign_name']}_report.xlsx"},
    )


# ── STATIC FRONTEND ──────────────────────────────────────────────────────────
# Serves the dashboard HTML/JS/CSS. Mounted last so /api/* routes take priority.

app.mount("/", StaticFiles(directory="static", html=True), name="static")
