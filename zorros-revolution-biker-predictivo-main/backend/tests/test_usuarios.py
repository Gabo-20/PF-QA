"""Pruebas de administracion de usuarios, roles y contraseñas.

Usan una base SQLite aislada por prueba, de modo que no tocan la base real ni
dependen del orden de ejecucion.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models, schemas
from app.database import Base
from app.deps import get_db
from app.main import app
from app.security import hash_password, verify_password

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


@pytest.fixture()
def h_admin(cliente):
    return _token(cliente, "admin@test.com", CLAVE_ADMIN)


@pytest.fixture()
def h_cajero(cliente):
    return _token(cliente, "cajero@test.com", CLAVE_CAJERO)


class TestPoliticaDePassword:
    @pytest.mark.parametrize(
        "clave,fragmento",
        [
            ("corta1", "al menos 10"),
            ("soloLetrasAqui", "un número"),
            ("1234567890123", "una letra"),
        ],
    )
    def test_rechaza_claves_debiles(self, clave, fragmento):
        with pytest.raises(ValueError) as exc:
            schemas.validar_password(clave)
        assert fragmento in str(exc.value)

    def test_acepta_una_valida(self):
        assert schemas.validar_password("ClaveBuena123") == "ClaveBuena123"

    def test_la_api_rechaza_una_clave_debil_al_crear(self, cliente, h_admin):
        r = cliente.post("/users", headers=h_admin, json={
            "nombre": "Nuevo", "email": "nuevo@test.com", "password": "abc", "rol": "cajero"})
        assert r.status_code == 422


class TestCreacionYAlmacenamiento:
    def test_la_contrasena_se_guarda_hasheada_nunca_en_claro(self, cliente, h_admin, db_sesion):
        clave = "OtraClave456"
        r = cliente.post("/users", headers=h_admin, json={
            "nombre": "Nuevo", "email": "nuevo@test.com", "password": clave, "rol": "cajero"})
        assert r.status_code == 201

        # La respuesta no expone ni la clave ni el hash
        assert "password" not in r.json()
        assert "password_hash" not in r.json()

        creado = db_sesion.query(models.User).filter_by(email="nuevo@test.com").first()
        assert creado.password_hash != clave
        assert creado.password_hash.startswith("$2")  # bcrypt
        assert verify_password(clave, creado.password_hash)

    def test_el_usuario_creado_puede_iniciar_sesion(self, cliente, h_admin):
        cliente.post("/users", headers=h_admin, json={
            "nombre": "Nuevo", "email": "nuevo@test.com", "password": "ClaveNueva123", "rol": "cajero"})
        assert cliente.post("/auth/login", json={
            "email": "nuevo@test.com", "password": "ClaveNueva123"}).status_code == 200

    def test_rol_invalido_se_rechaza(self, cliente, h_admin):
        r = cliente.post("/users", headers=h_admin, json={
            "nombre": "X", "email": "x@test.com", "password": "ClaveBuena123", "rol": "superusuario"})
        assert r.status_code == 422


class TestControlDeAcceso:
    def test_un_cajero_no_puede_listar_usuarios(self, cliente, h_cajero):
        assert cliente.get("/users", headers=h_cajero).status_code == 403

    def test_un_cajero_no_puede_crear_usuarios(self, cliente, h_cajero):
        r = cliente.post("/users", headers=h_cajero, json={
            "nombre": "X", "email": "x@test.com", "password": "ClaveBuena123", "rol": "admin"})
        assert r.status_code == 403

    def test_un_cajero_no_puede_restablecer_claves_ajenas(self, cliente, h_cajero, db_sesion):
        admin = db_sesion.query(models.User).filter_by(email="admin@test.com").first()
        r = cliente.put(f"/users/{admin.id}/password", headers=h_cajero,
                        json={"password_nueva": "Secuestrada123"})
        assert r.status_code == 403

    def test_sin_token_no_se_accede(self, cliente):
        assert cliente.get("/users").status_code == 401


class TestCambioDeRol:
    def test_admin_cambia_el_rol_de_otro(self, cliente, h_admin, db_sesion):
        cajero = db_sesion.query(models.User).filter_by(email="cajero@test.com").first()
        r = cliente.put(f"/users/{cajero.id}/rol", headers=h_admin, json={"rol": "admin"})
        assert r.status_code == 200 and r.json()["rol"] == "admin"

    def test_no_puede_quitarse_a_si_mismo_el_rol_admin(self, cliente, h_admin, db_sesion):
        admin = db_sesion.query(models.User).filter_by(email="admin@test.com").first()
        r = cliente.put(f"/users/{admin.id}/rol", headers=h_admin, json={"rol": "cajero"})
        assert r.status_code == 409
        assert "ti mismo" in r.json()["detail"]

    def test_no_puede_degradarse_al_ultimo_admin(self, cliente, h_admin, db_sesion):
        """Con dos admins, degradar a otro es valido; al quedar uno solo, no."""
        otro = models.User(nombre="Admin Dos", email="admin2@test.com",
                           password_hash=hash_password(CLAVE_ADMIN),
                           rol=models.RolUsuario.admin, activo=True)
        db_sesion.add(otro)
        db_sesion.commit()

        # Ahora hay dos: degradar al segundo si se permite
        r = cliente.put(f"/users/{otro.id}/rol", headers=h_admin, json={"rol": "cajero"})
        assert r.status_code == 200

        # Queda uno solo y es quien hace la peticion: bloqueado
        admin = db_sesion.query(models.User).filter_by(email="admin@test.com").first()
        r = cliente.put(f"/users/{admin.id}/rol", headers=h_admin, json={"rol": "cajero"})
        assert r.status_code == 409


class TestEstado:
    def test_no_puede_desactivarse_a_si_mismo(self, cliente, h_admin, db_sesion):
        admin = db_sesion.query(models.User).filter_by(email="admin@test.com").first()
        r = cliente.put(f"/users/{admin.id}/estado", headers=h_admin, json={"activo": False})
        assert r.status_code == 409
        assert "propia cuenta" in r.json()["detail"]

    def test_desactivar_a_otro_si_se_permite(self, cliente, h_admin, db_sesion):
        cajero = db_sesion.query(models.User).filter_by(email="cajero@test.com").first()
        r = cliente.put(f"/users/{cajero.id}/estado", headers=h_admin, json={"activo": False})
        assert r.status_code == 200 and r.json()["activo"] is False

    def test_un_usuario_desactivado_no_puede_entrar(self, cliente, h_admin, db_sesion):
        cajero = db_sesion.query(models.User).filter_by(email="cajero@test.com").first()
        cliente.put(f"/users/{cajero.id}/estado", headers=h_admin, json={"activo": False})
        r = cliente.post("/auth/login", json={"email": "cajero@test.com", "password": CLAVE_CAJERO})
        assert r.status_code == 401


class TestRestablecerPassword:
    def test_admin_restablece_la_de_otro_y_la_anterior_deja_de_servir(self, cliente, h_admin, db_sesion):
        cajero = db_sesion.query(models.User).filter_by(email="cajero@test.com").first()
        r = cliente.put(f"/users/{cajero.id}/password", headers=h_admin,
                        json={"password_nueva": "ClaveReseteada123"})
        assert r.status_code == 200

        assert cliente.post("/auth/login", json={
            "email": "cajero@test.com", "password": CLAVE_CAJERO}).status_code == 401
        assert cliente.post("/auth/login", json={
            "email": "cajero@test.com", "password": "ClaveReseteada123"}).status_code == 200

    def test_usuario_inexistente(self, cliente, h_admin):
        r = cliente.put("/users/9999/password", headers=h_admin, json={"password_nueva": "ClaveBuena123"})
        assert r.status_code == 404


class TestCambiarMiPassword:
    def test_cualquier_rol_puede_cambiar_la_suya(self, cliente, h_cajero):
        r = cliente.put("/auth/me/password", headers=h_cajero, json={
            "password_actual": CLAVE_CAJERO, "password_nueva": "MiClaveNueva123"})
        assert r.status_code == 200
        assert cliente.post("/auth/login", json={
            "email": "cajero@test.com", "password": "MiClaveNueva123"}).status_code == 200

    def test_exige_la_contrasena_actual(self, cliente, h_cajero):
        """Sin esto, un token robado bastaria para apoderarse de la cuenta."""
        r = cliente.put("/auth/me/password", headers=h_cajero, json={
            "password_actual": "EquivocadaTotal1", "password_nueva": "MiClaveNueva123"})
        assert r.status_code == 400
        assert "actual no es correcta" in r.json()["detail"]

    def test_la_nueva_debe_ser_distinta(self, cliente, h_cajero):
        r = cliente.put("/auth/me/password", headers=h_cajero, json={
            "password_actual": CLAVE_CAJERO, "password_nueva": CLAVE_CAJERO})
        assert r.status_code == 400

    def test_la_nueva_tambien_cumple_la_politica(self, cliente, h_cajero):
        r = cliente.put("/auth/me/password", headers=h_cajero, json={
            "password_actual": CLAVE_CAJERO, "password_nueva": "corta"})
        assert r.status_code == 422


class TestSeedSinClavesEnCodigo:
    def test_el_seed_ya_no_lleva_contrasenas_escritas(self):
        from app import seed_data
        for u in seed_data.USUARIOS_DEMO:
            assert "password" not in u, "el seed no debe llevar contraseñas en el código"

    def test_genera_claves_que_cumplen_la_politica(self):
        from app.seed_data import _password_aleatoria
        for _ in range(20):
            schemas.validar_password(_password_aleatoria())

    def test_las_claves_generadas_no_se_repiten(self):
        from app.seed_data import _password_aleatoria
        assert len({_password_aleatoria() for _ in range(50)}) == 50
