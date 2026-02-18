import multiprocessing
import os


def post_fork(server, worker):
    """Only let worker #1 run the scheduler; all others clear the flag."""
    if worker.age == 1:
        os.environ['ZLM_SCHEDULER_ENABLED'] = '1'
    else:
        os.environ.pop('ZLM_SCHEDULER_ENABLED', None)

# Bind
bind = os.environ.get('GUNICORN_BIND', '0.0.0.0:8000')
workers = int(os.environ.get('GUNICORN_WORKERS', min(4, multiprocessing.cpu_count())))
worker_class = 'uvicorn.workers.UvicornWorker'
timeout = 120
keepalive = 5
preload_app = True

# Logging — stdout/stderr for container log drivers
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')

# Process naming
proc_name = 'zimbra-lifecycle'

# Security
limit_request_line = 4096
limit_request_fields = 50
