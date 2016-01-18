from datetime import timedelta

from celery_app import celery

# noinspection PyUnresolvedReferences
import helpers.background

update_frequency = 300

# Routine Cache Checks
celery.conf.CELERYBEAT_SCHEDULE = {
    "JF-Contracts-Refresh": {
        "task": "helpers.background.jf_update",
        "schedule": timedelta(seconds=update_frequency),
        "kwargs": {"celery_time": update_frequency}
    },
}
