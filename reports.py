"""
Reports & Analytics Module
CSV/Excel export, dashboard analytics
"""

import io
from datetime import datetime

import pandas as pd


def export_report_csv(leads: list[dict]) -> bytes:
    df = pd.DataFrame(leads)
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def export_report_excel(leads: list[dict], campaign_name: str) -> bytes:
    df = pd.DataFrame(leads)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Campaign Report")
        # Summary sheet
        summary = pd.DataFrame({
            "Metric": ["Total", "Sent", "Failed", "Success Rate"],
            "Value": [
                len(df),
                len(df[df["status"] == "sent"]),
                len(df[df["status"] == "failed"]),
                f"{len(df[df['status']=='sent'])/len(df)*100:.1f}%" if len(df) else "0%",
            ],
        })
        summary.to_excel(writer, index=False, sheet_name="Summary")
    return buf.getvalue()


def build_analytics_chart_data(campaigns: list[dict]) -> dict:
    """Prepare data for Streamlit charts."""
    names = [c["campaign_name"][:20] for c in campaigns]
    sent = [c["sent_count"] for c in campaigns]
    failed = [c["failed_count"] for c in campaigns]
    return {"names": names, "sent": sent, "failed": failed}
