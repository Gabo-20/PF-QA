import os

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")

# Cada worker carga pandas + scikit-learn + el modelo en memoria (~250-350 MB).
# En el VPS actual (1 núcleo, ~1.9 GB libres compartidos con otros proyectos) la
# fórmula clásica `cpu_count()*2+1` provoca riesgo de OOM, y con un solo núcleo
# más workers tampoco aportan rendimiento. Se fija por entorno y sin ese cálculo.
workers = int(os.getenv("GUNICORN_WORKERS", "2"))

worker_class = "uvicorn.workers.UvicornWorker"

# El reentrenamiento corre dentro del request (ver ml/forecasting.entrenar_modelo).
# Con un histórico real supera con holgura los 60 s originales y el worker moría a
# media faena. Mientras el entrenamiento no sea asíncrono, el timeout debe cubrirlo.
timeout = int(os.getenv("GUNICORN_TIMEOUT", "300"))
graceful_timeout = 30
max_requests = 1000
max_requests_jitter = 100

accesslog = "-"
errorlog = "-"
