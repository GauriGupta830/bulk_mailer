"""
AI Features Module
Uses Groq (free tier) for AI email generation, subject lines, lead scoring.
"""

import os
from groq import Groq

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
MODEL = "llama-3.3-70b-versatile"


def _client() -> Groq:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set in environment.")
    return Groq(api_key=GROQ_API_KEY)


# ── AI Email Generator ────────────────────────────────────────────────────────

def generate_email(prompt: str, tone: str = "professional") -> dict:
    """
    Generate a complete cold email based on user's brief.
    Returns {"subject": str, "body": str}
    """
    system = (
        "You are an expert cold email copywriter with 10+ years of experience. "
        "Generate high-converting, personalized cold emails. "
        "Use these placeholders: {Name}, {Email}, {Company}, {Phone}. "
        "Return ONLY a JSON object with keys: subject (string) and body (string). "
        "No markdown, no explanation, just the JSON."
    )
    user_msg = (
        f"Write a {tone} cold email for: {prompt}\n"
        "Use {Name} and {Company} naturally in the email.\n"
        "Make it concise, compelling, and end with a clear CTA."
    )
    resp = _client().chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user_msg}],
        temperature=0.7,
        max_tokens=800,
    )
    import json, re
    raw = resp.choices[0].message.content.strip()
    # Strip markdown if present
    raw = re.sub(r"```json|```", "", raw).strip()
    try:
        return json.loads(raw)
    except Exception:
        # Fallback: return raw as body
        return {"subject": "Connecting with {Company}", "body": raw}


# ── AI Styled HTML Email Generator ────────────────────────────────────────────

def generate_html_email(brief: str, brand_name: str = "", cta_label: str = "", tone: str = "professional") -> dict:
    """
    Generate a complete, professional HTML email (inline-styled, card-based layout —
    similar to a welcome/onboarding email) from a short brief description of what
    the email should contain.
    Returns {"subject": str, "html": str}
    """
    system = (
        "You are an expert email designer who builds clean, professional HTML emails "
        "using ONLY inline CSS (no <style> blocks, no external CSS, no classes) because "
        "most email clients strip anything else. "
        "Structure: a centered card (max-width 600px) with a white background, light grey "
        "page background, a heading, a short intro paragraph, an optional numbered list of "
        "2-4 short 'next step' items each with a bold title and one-line description, an "
        "optional bold CTA button (dark background, white text, rounded corners), and a "
        "muted footer line with a support contact if given. "
        "Use placeholders {Name} and {Company} naturally in the greeting/body where it makes sense. "
        "Return ONLY a JSON object with two keys: 'subject' (string) and 'html' (a single-line "
        "or minimally-wrapped full HTML string starting with a <div> or <table> wrapper — do NOT "
        "include <html>, <head>, or <body> tags). No markdown, no explanation, just the JSON."
    )
    user_msg = (
        f"Brief / what to include: {brief}\n"
        f"Tone: {tone}\n"
    )
    if brand_name:
        user_msg += f"Brand / sender name: {brand_name}\n"
    if cta_label:
        user_msg += f"Call-to-action button label: {cta_label}\n"

    resp = _client().chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user_msg}],
        temperature=0.6,
        max_tokens=1800,
    )
    import json, re
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"```json|```html|```", "", raw).strip()
    try:
        result = json.loads(raw)
        if "subject" not in result or "html" not in result:
            raise ValueError("missing keys")
        return result
    except Exception:
        # Fallback: treat the whole response as the HTML body
        return {"subject": f"A message from {brand_name or 'us'}", "html": raw}


# ── AI Subject Line Generator ─────────────────────────────────────────────────

def generate_subjects(context: str, count: int = 10) -> list[str]:
    """Generate N high-converting email subject lines."""
    system = (
        "You are a world-class email marketing specialist. "
        "Generate high-converting email subject lines. "
        f"Return ONLY a JSON array of {count} subject line strings. No explanation."
    )
    resp = _client().chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": f"Context: {context}"}],
        temperature=0.8,
        max_tokens=500,
    )
    import json, re
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"```json|```", "", raw).strip()
    try:
        subjects = json.loads(raw)
        return subjects[:count]
    except Exception:
        return [line.strip("- ") for line in raw.split("\n") if line.strip()][:count]


# ── AI Lead Scoring ───────────────────────────────────────────────────────────

def ai_score_leads(leads: list[dict]) -> list[dict]:
    """
    Classify each lead as hot / warm / cold using AI.
    Batch up to 20 leads per call.
    """
    if not leads:
        return leads

    import json

    system = (
        "You are a B2B sales analyst. Given a list of leads, classify each as "
        "'hot', 'warm', or 'cold' based on: company name quality, email domain, "
        "presence of company info. Return ONLY a JSON array of objects with keys "
        "'email' and 'score'. No explanation."
    )
    # Batch in groups of 20
    result_map: dict[str, str] = {}
    for i in range(0, len(leads), 20):
        batch = leads[i: i + 20]
        batch_data = [
            {"email": l.get("email", ""), "name": l.get("name", ""),
             "company": l.get("company", "")}
            for l in batch
        ]
        try:
            resp = _client().chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(batch_data)},
                ],
                temperature=0.3,
                max_tokens=600,
            )
            raw = resp.choices[0].message.content.strip()
            raw = re.sub(r"```json|```", "", raw).strip()
            scores = json.loads(raw)
            for s in scores:
                result_map[s["email"]] = s.get("score", "cold")
        except Exception:
            pass  # fallback to existing heuristic score

    import re
    for lead in leads:
        if lead.get("email") in result_map:
            lead["lead_score"] = result_map[lead["email"]]
    return leads
