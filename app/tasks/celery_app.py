from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "mediadownuzbot",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.media_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Tashkent",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    worker_max_memory_per_child=750000,
    task_track_started=True,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 7200},
    task_soft_time_limit=settings.MAX_DOWNLOAD_SECONDS,
    task_time_limit=settings.MAX_DOWNLOAD_SECONDS + 60,
    beat_schedule={
        "cleanup-stale-media": {
            "task": "media.cleanup_stale",
            "schedule": 1800.0,
        }
    },
)
