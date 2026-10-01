"""Pruebas del endpoint que informa el último entrenamiento del modelo.

La pantalla de pronóstico mostraba "Sin entrenar" al cargar aunque existiera
un modelo publicado, porque solo conocía el resultado del botón Recalibrar.
"""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
from app.deps import get_db
from app.main import app
from app.security import hash_password

CLAVE_ADMIN = "AdminSegura123"
CLAVE_CAJERO = "CajeroSeguro123"


@pytest.fixture()
def db_sesion():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    Sesion = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    sesion = Sesion()
    sesion.add_all(
        [
            models.User(nombre="Admin Uno", email="admin@test.com",
                        password_hash=hash_password(CLAVE_ADMIN),
                        rol=models.RolUsuario.admin, activo=True),
            models.User(nombre="Cajero Uno", email="cajero@test.com",
                        password_hash=hash_password(CLAVE_CAJERO),
                        rol=models.RolUsuario.cajero, activo=True),
        ]
    )
    sesion.commit()

    def _get_db():
        yield sesion

    app.dependency_overrides[get_db] = _get_db
    yield sesion
    app.dependency_overrides.clear()
    sesion.close()


@pytest.fixture()
def cliente(db_sesion):
    return TestClient(app)


def _token(cliente, email, password):
    r = cliente.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _run(algoritmo, version, mase=None, wape=None, mejora=None, motivo=None):
    return models.ModelRun(
        algoritmo=algoritmo, version=version, mase=mase, wape=wape,
        parametros_json=json.dumps({"decision": {"mejora_pct": mejora, "motivo": motivo}}),
    )


class TestEstadoDelModelo:
    def test_sin_entrenamientos_informa_que_no_hay_modelo(self, cliente, db_sesion):
        h = _token(cliente, "admin@test.com", CLAVE_ADMIN)
        r = cliente.get("/predictions/model", headers=h)
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        assert cuerpo["entrenado"] is False
        assert cuerpo["publicado"] is False
        assert cuerpo["algoritmo"] is None

    def test_devuelve_el_ultimo_entrenamiento_publicado(self, cliente, db_sesion):
        db_sesion.add(_run("GradientBoostingRegressor", "20260901000000", 0.95, 30.0, 5.0))
        db_sesion.add(_run("GradientBoostingRegressor", "20260919130723", 0.803, 43.99, 22.35, "supera la referencia"))
        db_sesion.commit()
        h = _token(cliente, "admin@test.com", CLAVE_ADMIN)
        cuerpo = cliente.get("/predictions/model", headers=h).json()
        assert cuerpo["entrenado"] is True
        assert cuerpo["publicado"] is True
        assert cuerpo["algoritmo"] == "GradientBoostingRegressor"
        assert cuerpo["version"] == "20260919130723"
        assert cuerpo["mase"] == 0.803
        assert cuerpo["wape"] == 43.99
        assert cuerpo["mejora_vs_baseline_pct"] == 22.35
        assert cuerpo["fecha"] is not None

    def test_un_entrenamiento_no_publicado_se_reporta_como_tal(self, cliente, db_sesion):
        db_sesion.add(_run("GradientBoostingRegressor", "20260901000000", 0.95, 30.0, 12.0))
        db_sesion.add(_run("no_publicado (mejor: naive_estacional)", "20260919000000", 1.1, 50.0, -3.0,
                           "no supera la mejora mínima"))
        db_sesion.commit()
        h = _token(cliente, "admin@test.com", CLAVE_ADMIN)
        cuerpo = cliente.get("/predictions/model", headers=h).json()
        assert cuerpo["entrenado"] is True
        assert cuerpo["publicado"] is False
        assert cuerpo["motivo"] == "no supera la mejora mínima"
        assert cuerpo["mejora_vs_baseline_pct"] == -3.0

    def test_tolera_un_registro_sin_detalle_json(self, cliente, db_sesion):
        db_sesion.add(models.ModelRun(algoritmo="GradientBoostingRegressor", version="20260801000000"))
        db_sesion.commit()
        h = _token(cliente, "admin@test.com", CLAVE_ADMIN)
        cuerpo = cliente.get("/predictions/model", headers=h).json()
        assert cuerpo["entrenado"] is True
        assert cuerpo["mejora_vs_baseline_pct"] is None
        assert cuerpo["motivo"] is None

    def test_un_cajero_no_puede_consultarlo(self, cliente, db_sesion):
        h = _token(cliente, "cajero@test.com", CLAVE_CAJERO)
        assert cliente.get("/predictions/model", headers=h).status_code == 403
