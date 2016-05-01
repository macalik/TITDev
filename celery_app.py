from flask import g
from app import app, app_mongo, app_redis
from celery import Celery

celery = Celery(app.import_name)
celery.conf.update(app.config)

task_base = celery.Task


class ContextTask(task_base):
    abstract = True

    def __call__(self, *args, **kwargs):
        with app.app_context():
            # Application context for databases
            g.mongo = app_mongo
            g.redis = app_redis

            return task_base.__call__(self, *args, **kwargs)

celery.Task = ContextTask

# Security Concerns (http://docs.celeryproject.org/en/latest/faq.html#is-celery-dependent-on-pickle)
celery.conf.CELERY_ACCEPT_CONTENT = ["json", "application/json"]
celery.conf.CELERY_TASK_SERIALIZER = "json"
celery.conf.CELERY_RESULT_SERIALIZER = "json"
