"""
Excel / CSV Processing Module
Validates, cleans, and scores leads from uploaded files.
"""

import io
import json
import re
from typing import Any

import pandas as pd


EXPECTED_COLUMNS = {"name", "email", "company", "phone"}
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

# High-value domains → warm/hot scoring hints
PREMIUM_DOMAINS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
    "icloud.com", "protonmail.com",
}


def process_file(file_bytes: bytes, filename: str) -> dict[str, Any]:
    """
    Parse Excel/CSV file and return:
      {
        "df": pd.DataFrame (cleaned),
        "columns": list[str],
        "missing_expected": list[str],
        "extra_columns": list[str],
        "total": int,
        "duplicates_removed": int,
        "invalid_emails": int,
        "errors": list[str],
      }
    """
    errors: list[str] = []

    # ── Parse ────────────────────────────────────────────────────────────────
    try:
        if filename.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_bytes))
        else:
            df = pd.read_excel(io.BytesIO(file_bytes))
    except Exception as e:
        return {"errors": [f"Could not parse file: {e}"], "df": None}

    if df.empty:
        return {"errors": ["Uploaded file is empty."], "df": None}

    # Normalize column names
    df.columns = [str(c).strip().title() for c in df.columns]

    detected_cols = list(df.columns)
    lower_cols = {c.lower() for c in detected_cols}
    missing_expected = [c.title() for c in EXPECTED_COLUMNS if c not in lower_cols]
    extra_cols = [c for c in detected_cols if c.lower() not in EXPECTED_COLUMNS]

    # ── Email column is mandatory ─────────────────────────────────────────────
    if "Email" not in df.columns:
        return {"errors": ["'Email' column not found. Please include an Email column."], "df": None}

    original_count = len(df)

    # Drop rows with missing email
    df = df.dropna(subset=["Email"])
    df["Email"] = df["Email"].astype(str).str.strip().str.lower()

    # Remove invalid emails
    valid_mask = df["Email"].apply(lambda e: bool(EMAIL_REGEX.match(e)))
    invalid_count = (~valid_mask).sum()
    df = df[valid_mask].copy()

    # Remove duplicates
    before_dedup = len(df)
    df = df.drop_duplicates(subset=["Email"])
    duplicates_removed = before_dedup - len(df)

    # Lead scoring
    df["LeadScore"] = df["Email"].apply(_score_lead)

    # Serialize extra columns to JSON per row
    base_cols = [c for c in df.columns if c.lower() in EXPECTED_COLUMNS or c == "LeadScore"]
    extra_data_cols = [c for c in df.columns if c not in base_cols]
    if extra_data_cols:
        df["ExtraData"] = df[extra_data_cols].apply(
            lambda row: json.dumps(row.to_dict()), axis=1
        )
    else:
        df["ExtraData"] = "{}"

    return {
        "df": df,
        "columns": detected_cols,
        "missing_expected": missing_expected,
        "extra_columns": extra_cols,
        "total": len(df),
        "duplicates_removed": duplicates_removed,
        "invalid_emails": int(invalid_count),
        "original_count": original_count,
        "errors": errors,
    }


def _score_lead(email: str) -> str:
    """Simple heuristic lead scoring."""
    domain = email.split("@")[-1] if "@" in email else ""

    # Corporate domains → warmer leads
    if domain and domain not in PREMIUM_DOMAINS:
        return "hot"

    # Gmail/Yahoo personal → less qualified
    if domain in PREMIUM_DOMAINS:
        return "warm"

    return "cold"


def personalize_email(template: str, row: dict) -> str:
    """Replace {Column} or {{Column}} placeholders with actual values (case-insensitive)."""
    # Build a lowercase-keyed lookup so {Name}, {{Name}}, {name}, {{name}} all match
    lower_row = {str(k).lower(): v for k, v in row.items()}

    def _replace(match: "re.Match") -> str:
        key = match.group(1).strip().lower()
        if key in lower_row:
            value = lower_row[key]
            return str(value) if pd.notna(value) else ""
        return match.group(0)  # no matching column, leave placeholder untouched

    # Matches {{Name}}, {Name}, {{name}}, {name}, etc. — single or double braces, any case
    pattern = re.compile(r"\{\{?\s*(\w+)\s*\}?\}")
    return pattern.sub(_replace, template)


def df_to_leads(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame rows to lead dicts for DB insertion."""
    leads = []
    for _, row in df.iterrows():
        leads.append({
            "name": row.get("Name", ""),
            "email": row["Email"],
            "company": row.get("Company", ""),
            "phone": str(row.get("Phone", "")),
            "extra_data": row.get("ExtraData", "{}"),
            "lead_score": row.get("LeadScore", "cold"),
        })
    return leads