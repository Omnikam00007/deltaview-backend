from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "deltaview",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.sync"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    beat_schedule={
        # Runs every day at 3:35 PM IST (10:05 UTC)
        "daily-portfolio-snapshot": {
            "task": "app.tasks.sync.take_daily_snapshot",
            "schedule": 3600 * 24,  # replace with crontab in production
        },
    },
)
