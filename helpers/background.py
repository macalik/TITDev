from functools import wraps

from celery_app import celery, app, g, app_mongo

from helpers.caches import contracts


def needs_database():
    def decorator(function):
        @wraps(function)
        def decorated_function(*args, **kwargs):
            with app.app_context():
                g.mongo = app_mongo
                return function(*args, **kwargs)
        return decorated_function
    return decorator


@celery.task()
def add_together(a, b):
    return a + b


@celery.task(ignore_result=True)
@needs_database()
def jf_update(*args, **kwargs):
    contracts(*args, **kwargs)
