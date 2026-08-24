"""
Gunicorn configuration for production Django application.

Supports:
  - Long-lived SSE connections
  - Concurrent webhook processing
  - Graceful shutdown
"""
import os
import multiprocessing

# Bind to TCP socket (Docker network)
bind = '0.0.0.0:8000'

# Workers and threads
workers = max(2, multiprocessing.cpu_count())
threads = 4  # per worker for gthread
worker_class = 'gthread'  # supports long-lived connections

# Timeouts and keepalive
timeout = 120  # seconds
graceful_timeout = 60
keepalive = 65

# Request handling
max_requests = 10000
max_requests_jitter = 1000

# Logging
accesslog = '-'  # stdout
errorlog = '-'   # stderr
loglevel = 'info'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'taxicarga-api'

# Enable proxy headers
forwarded_allow_ips = '*'
secure_scheme_header = 'X-FORWARDED-PROTO'
secure_ssl_redirect = False  # Nginx handles HTTPS

# Server mechanics
daemon = False
pidfile = None
umask = 0o022
tmp_upload_dir = None

# Server hooks
def on_starting(server):
    print('[gunicorn] Server starting')

def when_ready(server):
    print(f'[gunicorn] Workers ready: {workers}')

def on_exit(server):
    print('[gunicorn] Server exiting')
