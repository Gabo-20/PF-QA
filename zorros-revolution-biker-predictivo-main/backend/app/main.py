from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import Base, engine
from .routers import (
    auth_router,
    dashboard_router,
    inventory_router,
    predictions_router,
    products_router,
    sales_router,
    users_router,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.APP_NAME)

origins = ["*"] if settings.CORS_ORIGINS.strip() == "*" else [o.strip() for o in settings.CORS_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(products_router.router)
app.include_router(sales_router.router)
app.include_router(inventory_router.router)
app.include_router(dashboard_router.router)
app.include_router(predictions_router.router)
app.include_router(users_router.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME}


# Sirve el frontend estático (HTML/CSS/JS) desde el mismo servidor FastAPI.
# Se monta al final para que las rutas de la API definidas arriba tengan prioridad.
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
