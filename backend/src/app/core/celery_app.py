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
# Если воркер аварийно умрёт посреди обработки (SIGKILL/OOM), Celery не
# получит ack и передаст задачу другому/перезапущенному воркеру сам —
# без этого таск бы считался выполненным сразу после получения, и
# аварийная смерть воркера оставляла бы файл в processing навсегда.
celery_app.conf.task_acks_late = True
celery_app.conf.task_reject_on_worker_lost = True
# Redis возвращает неподтверждённую задачу после visibility_timeout.
# Значение должно быть больше максимального времени выполнения задачи,
# иначе нормально выполняющаяся задача может быть продублирована.
celery_app.conf.broker_transport_options = {"visibility_timeout": 3600}
