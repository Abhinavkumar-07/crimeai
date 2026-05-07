"""
Celery application factory — final schedule including NLP pending cleanup.
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "crimeai",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks.ml_tasks",
        "app.workers.tasks.nlp_tasks",
        "app.workers.tasks.alert_tasks",
        "app.workers.tasks.report_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    task_default_queue="default",
    task_queues={
        "default": {"exchange": "default", "routing_key": "default"},
        "ml":      {"exchange": "ml",      "routing_key": "ml"},
        "nlp":     {"exchange": "nlp",     "routing_key": "nlp"},
    },
    task_routes={
        "app.workers.tasks.ml_tasks.*":    {"queue": "ml"},
        "app.workers.tasks.nlp_tasks.*":   {"queue": "nlp"},
        "app.workers.tasks.alert_tasks.*": {"queue": "default"},
        "app.workers.tasks.report_tasks.*":{"queue": "default"},
    },
    beat_schedule={
        # ML
        "hotspot-prediction-hourly": {
            "task": "app.workers.tasks.ml_tasks.run_hotspot_prediction",
            "schedule": crontab(minute=0),
        },
        "crime-clustering-6h": {
            "task": "app.workers.tasks.ml_tasks.run_crime_clustering",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        "batch-embedding-4h": {
            "task": "app.workers.tasks.ml_tasks.run_batch_embedding",
            "schedule": crontab(minute=30, hour="*/4"),
        },
        # NLP
        "process-pending-firs-30min": {
            "task": "app.workers.tasks.nlp_tasks.process_pending_firs",
            "schedule": crontab(minute="*/30"),
        },
        # Alerts
        "risk-alert-check": {
            "task": "app.workers.tasks.alert_tasks.check_high_risk_areas",
            "schedule": crontab(minute="*/15"),
        },
    },
)
