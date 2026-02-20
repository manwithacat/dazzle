web: python -m dazzle dnr serve --local --host 0.0.0.0 --port $PORT --api-port 8111
worker: celery -A dazzle.core.process.celery_tasks worker -l info -Q process,celery --concurrency 2
beat: celery -A dazzle.core.process.celery_tasks beat -l info
