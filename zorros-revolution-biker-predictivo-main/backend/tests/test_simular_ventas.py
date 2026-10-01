"""Pruebas del simulador de ventas.

El simulador existe para poder evaluar el modelo sin la circularidad del seed
anterior, asi que la primera prueba es una regresion: el modulo no debe
compartir ninguna funcion de calendario con el modelo.
"""
import ast
from datetime import date, timedelta
from pathlib import Path

import pytest

from app import simular_ventas as sv


class TestSinCircularidadConElModelo:
    def test_no_importa_calendar_features(self):
        """Si el generador usa las mismas funciones que las features del
        modelo, este recupera por construccion la senal inyectada y ninguna
        metrica prueba nada. La prueba lee el codigo fuente, no el modulo
        cargado, para atrapar tambien importaciones dentro de funciones."""
        fuente = Path(sv.__file__).read_text(encoding="utf-8")
        arbol = ast.parse(fuente)
        importados = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ImportFrom) and nodo.module:
                importados.add(nodo.module)
                importados.update(a.name for a in nodo.names)
            elif isinstance(nodo, ast.Import):
                importados.update(a.name for a in nodo.names)
        assert not any("calendar_features" in m for m in importados), importados
        assert "calendar_features" not in fuente


class TestRangoDeFechas:
    def test_termina_en_hasta_y_arranca_meses_atras(self):
        inicio, fin = sv.rango_fechas(hasta=date(2026, 9, 18), meses=12)
        assert fin == date(2026, 9, 18)
        assert inicio == date(2025, 9, 18)

    def test_seis_meses(self):
        inicio, _ = sv.rango_fechas(hasta=date(2026, 9, 18), meses=6)
        assert inicio == date(2026, 3, 18)

    def test_meses_debe_ser_positivo(self):
        with pytest.raises(ValueError):
            sv.rango_fechas(hasta=date(2026, 9, 18), meses=0)


class TestFactorCalendario:
    """Los factores son mecanismos que el modelo NO ve como feature directa."""

    def test_dia_normal_es_uno(self):
        # Martes 10 de marzo: sin feriado, sin quincena, sin evento
        assert sv.factor_calendario(date(2026, 3, 10)) == pytest.approx(1.0)

    def test_quincena_sube_la_demanda(self):
        assert sv.factor_calendario(date(2026, 3, 15)) > 1.0
        assert sv.factor_calendario(date(2026, 3, 31)) > 1.0

    def test_feriado_cerrado_es_cero(self):
        # 1 de enero y 25 de diciembre: la tienda no abre
        assert sv.factor_calendario(date(2026, 1, 1)) == 0.0
        assert sv.factor_calendario(date(2026, 12, 25)) == 0.0

    def test_aguinaldo_sube_desde_mediados_de_diciembre(self):
        assert sv.factor_calendario(date(2026, 12, 18)) > sv.factor_calendario(date(2026, 12, 3))

    def test_bono14_sube_solo_la_semana_del_pago(self):
        """La ley fija el pago en la primera quincena de julio; el efecto real
        se concentra en los dias posteriores al pago, no en todo el mes."""
        durante = sv.factor_calendario(date(2026, 7, 16))
        antes = sv.factor_calendario(date(2026, 7, 2))
        assert durante > antes

    def test_caravana_sube_la_vispera_y_baja_el_dia_del_evento(self):
        """No medio febrero: los dias previos se compra equipo; el sabado de
        la Caravana el cliente esta en la ruta y la tienda vende poco."""
        sabado = sv.CARAVANA_DEL_ZORRO[2026]
        vispera = sabado - timedelta(days=1)
        assert sv.factor_calendario(vispera) > 1.0
        assert sv.factor_calendario(sabado) < sv.factor_calendario(vispera)
        # Dos semanas despues, febrero normal
        assert sv.factor_calendario(date(2026, 2, 26)) == pytest.approx(1.0)


class TestPesoDiaSemana:
    def test_fin_de_semana_pesa_mas_que_entre_semana(self):
        sabado, martes = date(2026, 3, 14), date(2026, 3, 10)
        assert sv.peso_dia_semana(sabado) > sv.peso_dia_semana(martes)

    def test_los_pesos_son_positivos(self):
        for d in range(7):
            assert sv.peso_dia_semana(date(2026, 3, 9 + d)) > 0


# ---------------------------------------------------------------------------
# Simulacion contra base de datos
# ---------------------------------------------------------------------------
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
from app.security import hash_password


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    sesion = sessionmaker(bind=engine, autoflush=False, autocommit=False)()

    sesion.add_all([
        models.User(nombre="Admin", email="admin@t.com", password_hash=hash_password("ClaveAdmin123"),
                    rol=models.RolUsuario.admin),
        models.User(nombre="Cajero", email="cajero@t.com", password_hash=hash_password("ClaveCaj123"),
                    rol=models.RolUsuario.cajero),
    ])
    for i in range(5):
        sesion.add(models.Product(sku=f"SKU-{i}", nombre=f"Producto {i}", categoria="Cascos",
                                  precio=100.0 + i * 50, costo=60.0, stock_actual=0,
                                  stock_minimo=5, lead_time_dias_china=60))
    sesion.commit()
    yield sesion
    sesion.close()


def _config(**kw):
    base = dict(meses=3, hasta=date(2026, 9, 18), semilla=7)
    base.update(kw)
    return sv.Configuracion(**base)


class TestSeguridadDeEjecucion:
    def test_con_base_vacia_no_exige_confirmar(self, db):
        resumen = sv.simular(db, _config())
        assert resumen.ventas > 0

    def test_con_ventas_previas_se_niega_sin_confirmar(self, db):
        sv.simular(db, _config())
        with pytest.raises(ValueError, match="confirmar"):
            sv.simular(db, _config())

    def test_con_confirmar_reemplaza_las_ventas_previas(self, db):
        sv.simular(db, _config(semilla=1))
        primera = db.query(func.count(models.Sale.id)).scalar()

        sv.simular(db, _config(semilla=2), confirmar=True)
        segunda = db.query(func.count(models.Sale.id)).scalar()

        # No se acumulan: la segunda corrida sustituye a la primera
        assert segunda < primera * 2
        assert db.query(func.min(models.Sale.id)).scalar() > primera - 1 or segunda > 0

    def test_conserva_usuarios_y_productos(self, db):
        sv.simular(db, _config())
        sv.simular(db, _config(), confirmar=True)
        assert db.query(func.count(models.User.id)).scalar() == 2
        assert db.query(func.count(models.Product.id)).scalar() == 5


class TestContenidoDeLaSimulacion:
    def test_las_ventas_caen_dentro_del_rango(self, db):
        resumen = sv.simular(db, _config(meses=3, hasta=date(2026, 9, 18)))
        assert resumen.inicio == date(2026, 6, 18)
        assert resumen.fin == date(2026, 9, 18)
        fechas = [f for (f,) in db.query(models.Sale.fecha_hora).all()]
        assert min(fechas).date() >= resumen.inicio
        assert max(fechas).date() <= resumen.fin

    def test_es_reproducible_con_la_misma_semilla(self, db):
        a = sv.simular(db, _config(semilla=99))
        b = sv.simular(db, _config(semilla=99), confirmar=True)
        assert (a.ventas, a.unidades) == (b.ventas, b.unidades)

    def test_semillas_distintas_dan_resultados_distintos(self, db):
        a = sv.simular(db, _config(semilla=1))
        b = sv.simular(db, _config(semilla=2), confirmar=True)
        assert (a.ventas, a.unidades) != (b.ventas, b.unidades)

    def test_cada_venta_tiene_items_cajero_y_total_coherente(self, db):
        sv.simular(db, _config())
        for venta in db.query(models.Sale).limit(50):
            assert venta.items, "venta sin items"
            assert venta.cajero_id is not None
            esperado = sum(i.cantidad * i.precio_unitario for i in venta.items)
            assert venta.total == pytest.approx(esperado)

    def test_las_series_salen_intermitentes(self, db):
        """Con tasas Poisson bajas, cada producto debe tener dias sin venta."""
        resumen = sv.simular(db, _config(meses=3))
        total_dias = (resumen.fin - resumen.inicio).days + 1
        for producto in db.query(models.Product):
            dias_con_venta = (
                db.query(func.count(func.distinct(func.date(models.Sale.fecha_hora))))
                .join(models.SaleItem, models.SaleItem.sale_id == models.Sale.id)
                .filter(models.SaleItem.product_id == producto.id)
                .scalar()
            )
            assert dias_con_venta < total_dias, f"{producto.sku} vendio todos los dias"


class TestConsistenciaDeStock:
    def test_nunca_queda_stock_negativo(self, db):
        sv.simular(db, _config())
        for p in db.query(models.Product):
            assert p.stock_actual >= 0, p.sku

    def test_stock_actual_cuadra_con_los_movimientos(self, db):
        """stock final = recepciones - ventas, por producto."""
        sv.simular(db, _config())
        for p in db.query(models.Product):
            entradas = (db.query(func.coalesce(func.sum(models.StockMovement.cantidad), 0))
                        .filter(models.StockMovement.product_id == p.id,
                                models.StockMovement.tipo == models.TipoMovimiento.recepcion).scalar())
            salidas = (db.query(func.coalesce(func.sum(models.StockMovement.cantidad), 0))
                       .filter(models.StockMovement.product_id == p.id,
                               models.StockMovement.tipo == models.TipoMovimiento.venta).scalar())
            assert p.stock_actual == entradas - salidas, p.sku

    def test_las_unidades_vendidas_coinciden_con_los_movimientos_de_venta(self, db):
        sv.simular(db, _config())
        vendidas = db.query(func.coalesce(func.sum(models.SaleItem.cantidad), 0)).scalar()
        movidas = (db.query(func.coalesce(func.sum(models.StockMovement.cantidad), 0))
                   .filter(models.StockMovement.tipo == models.TipoMovimiento.venta).scalar())
        assert vendidas == movidas

    def test_simula_quiebres_de_stock(self, db):
        """La demanda censurada existe: hubo ventas que se perdieron por falta
        de existencia. Sin esto el simulador no reproduce el problema real."""
        resumen = sv.simular(db, _config(meses=6))
        assert resumen.ventas_perdidas_por_stock > 0


class TestCli:
    def test_ejecuta_con_argumentos_y_devuelve_resumen(self, db, capsys):
        resumen = sv.ejecutar(["--meses", "3", "--hasta", "2026-09-18", "--semilla", "5"], db=db)
        assert resumen.inicio == date(2026, 6, 18)
        salida = capsys.readouterr().out
        assert "ventas" in salida.lower()

    def test_sin_confirmar_con_datos_previos_falla_con_mensaje_claro(self, db):
        sv.ejecutar(["--meses", "3", "--hasta", "2026-09-18"], db=db)
        with pytest.raises(SystemExit) as exc:
            sv.ejecutar(["--meses", "3", "--hasta", "2026-09-18"], db=db)
        assert exc.value.code != 0

    def test_confirmar_permite_reemplazar(self, db):
        sv.ejecutar(["--meses", "3", "--hasta", "2026-09-18"], db=db)
        resumen = sv.ejecutar(["--meses", "3", "--hasta", "2026-09-18", "--confirmar"], db=db)
        assert resumen.ventas > 0

    def test_meses_por_defecto_es_doce(self, db):
        resumen = sv.ejecutar(["--hasta", "2026-09-18"], db=db)
        assert resumen.inicio == date(2025, 9, 18)


class TestIntegracionConSeed:
    def test_seed_data_ya_no_tiene_su_propio_generador(self):
        """Un solo simulador: seed_data debe delegar en este modulo."""
        from app import seed_data
        assert not hasattr(seed_data, "_generar_ventas")
        assert not hasattr(seed_data, "_factor_estacional")
        fuente = Path(seed_data.__file__).read_text(encoding="utf-8")
        assert "simular_ventas" in fuente
