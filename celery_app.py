from flask import g
from app import app, app_mongo
from celery import Celery

celery = Celery(app.import_name, broker=app.config['CELERY_BROKER_URL'], backend=app.config["CELERY_RESULT_BACKEND"])
celery.conf.update(app.config)

task_base = celery.Task


class ContextTask(task_base):
    abstract = True

    def __call__(self, *args, **kwargs):
        with app.app_context():
            # Application context for databases
            g.mongo = app_mongo

            return task_base.__call__(self, *args, **kwargs)

celery.Task = ContextTask

