"""Loopback only; bounded workers and allowlisted logging."""

bind = "127.0.0.1:18000"
workers = 2
worker_class = "sync"
timeout = 30
graceful_timeout = 30
keepalive = 2
accesslog = None
errorlog = "-"
capture_output = False
logger_class = "config.gunicorn.SafeGunicornLogger"
forwarded_allow_ips = "127.0.0.1"
