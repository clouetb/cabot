import os

from cabot.settings_utils import environ_get_list

broker_url = environ_get_list(["CELERY_BROKER_URL", "CACHE_URL"])
broker_use_ssl = os.environ.get("CELERY_BROKER_USE_SSL", False)
CELERY_DEFAULT_QUEUE = os.environ.get("CELERY_DEFAULT_QUEUE", "celery")

# Set environment variable if you want to run tests without a redis instance
task_always_eager = environ_get_list(
    ["CELERY_ALWAYS_EAGER", "CELERY_TASK_ALWAYS_EAGER"], False
)
backend = os.environ.get("CELERY_RESULT_BACKEND", None)
task_default_queue = os.environ.get("CELERY_DEFAULT_QUEUE", "celery")

timezone = os.environ.get("TIME_ZONE", "Etc/UTC")
