import os
import multiprocessing

# Gunicorn Production ASGI Server Configuration for HealthSlip AI

host = os.getenv("HOST", "0.0.0.0")
port = os.getenv("PORT", "8005")
bind = f"{host}:{port}"

# Concurrency: 2-4 workers per CPU core recommended for I/O bound FastAPI
workers_per_core = 2
cores = multiprocessing.cpu_count()
default_workers = max(2, min(cores * workers_per_core, 8))
workers = int(os.getenv("WEB_CONCURRENCY", default_workers))

# Worker class for async FastAPI & WebSockets
worker_class = "uvicorn.workers.UvicornWorker"

# Timeouts & Keepalive
timeout = int(os.getenv("GUNICORN_TIMEOUT", 120))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", 5))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", 30))

# Logging
loglevel = os.getenv("LOG_LEVEL", "info")
accesslog = "-"
errorlog = "-"

print(f"[Production] Gunicorn configured on {bind} with {workers} Uvicorn ASGI workers.")
