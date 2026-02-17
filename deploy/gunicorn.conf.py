import multiprocessing

bind = 'unix:/run/zimbra-lifecycle/gunicorn.sock'
workers = min(4, multiprocessing.cpu_count())
worker_class = 'uvicorn.workers.UvicornWorker'
timeout = 120
keepalive = 5

# Logging
accesslog = '/root/zimbra-lifecycle-fastapi/data/logs/gunicorn_access.log'
errorlog = '/root/zimbra-lifecycle-fastapi/data/logs/gunicorn_error.log'
loglevel = 'info'

# Process naming
proc_name = 'zimbra-lifecycle'

# Security
limit_request_line = 4096
limit_request_fields = 50
