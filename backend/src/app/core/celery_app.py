"""Объект Celery-приложения.

Конфигурация брокера и backend'а (Redis) вынесена отдельно от FastAPI DI
(dependencies.py), так как это инфраструктура очереди задач, а не
HTTP-зависимость — разная ответственность, разные файлы.
"""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "file_tasks",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"],
)
celery_app.conf.broker_pool_limit = 10
