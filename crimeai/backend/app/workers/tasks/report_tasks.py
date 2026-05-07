"""
Celery PDF report generation tasks.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from celery import shared_task

from app.core.logging import get_logger

logger = get_logger(__name__)


@shared_task(
    bind=True,
    name="app.workers.tasks.report_tasks.generate_pdf_report",
    max_retries=2,
    queue="default",
)
def generate_pdf_report(self, report_type: str, params: dict) -> dict:
    """
    Generate a PDF crime report using reportlab.
    Supported types: summary | district | cluster | fir
    """
    logger.info("pdf_report_started", report_type=report_type, task_id=self.request.id)

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        )
        from datetime import datetime, timezone
        import io

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []

        # Title
        story.append(Paragraph(
            f"CrimeAI — {report_type.replace('_', ' ').title()} Report",
            styles['Title']
        ))
        story.append(Spacer(1, 12))
        story.append(Paragraph(
            f"Generated: {datetime.now(timezone.utc).strftime('%d %B %Y %H:%M UTC')}",
            styles['Normal']
        ))
        story.append(Spacer(1, 24))
        story.append(Paragraph("Report content will be populated based on live data.", styles['Normal']))

        doc.build(story)
        pdf_bytes = buffer.getvalue()
        size_kb = len(pdf_bytes) // 1024

        logger.info("pdf_report_complete", report_type=report_type, size_kb=size_kb)
        return {
            "status": "complete",
            "report_type": report_type,
            "size_kb": size_kb,
            "task_id": self.request.id,
        }

    except Exception as exc:
        logger.error("pdf_report_failed", error=str(exc))
        raise self.retry(exc=exc)
