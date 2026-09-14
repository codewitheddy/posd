"""
Production Gunicorn Configuration for Marid POS
Optimized for 10 Branches × 10 Selling Points (100+ Concurrent POS Terminals)
"""
import multiprocessing
import os

# Server Socket
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")
backlog = 2048

# Worker Processes & Concurrency
# Using gthread worker class: 8 workers * 4 threads = 32 concurrent worker threads
# Ideal for handling persistent Server-Sent Events (SSE) connections and high-throughput checkouts
workers = int(os.environ.get("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1 if multiprocessing.cpu_count() else 8))
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", 4))
worker_connections = 1000

# Worker Lifecycle & Memory Management
# Recycles workers periodically to prevent memory leaks in 24/7 retail environments
max_requests = 2000
max_requests_jitter = 100
timeout = 120
keepalive = 75
graceful_timeout = 30

# Performance
preload_app = True

# Process Naming
proc_name = "pos_gunicorn"

# Logging
accesslog = os.environ.get("GUNICORN_ACCESS_LOG", "-")  # stdout for Docker/Systemd
errorlog = os.environ.get("GUNICORN_ERROR_LOG", "-")
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%({X-Forwarded-For}i)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sµs'

def on_starting(server):
    server.log.info("Starting Marid POS High-Scale Production Server...")

def post_fork(server, worker):
    server.log.info(f"Worker spawned (pid: {worker.pid})")
