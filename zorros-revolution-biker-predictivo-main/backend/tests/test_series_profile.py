"""Pruebas del perfilamiento de series de demanda.

Los valores esperados estan calculados a mano en cada prueba. Es a proposito: si
se comparan las formulas contra lo que devuelve el propio codigo, la prueba pasa
igual cuando la formula esta mal.
"""
import numpy as np
import pandas as pd
import pytest

from app.ml import series_profile as sp


class TestPerfilDeSerie:
    def test_serie_intermitente_valores_calculados_a_mano(self):
        # 10 dias, ventas solo en 3 de ellos: [_, 2, _, _, 4, _, _, _, 6, _]
        unidades = np.array([0, 2, 0, 0, 4, 0, 0, 0, 6, 0], dtype=float)
        p = sp.perfil_de_serie(unidades)

        assert p["dias_historial"] == 10
        assert p["unidades_totales"] == 12.0
        assert p["media_diaria"] == pytest.approx(1.2)

        # 7 dias sin venta de 10
        assert p["proporcion_ceros"] == pytest.approx(0.7)

        # ADI = 10 dias / 3 dias con demanda
        assert p["adi"] == pytest.approx(10 / 3)

        # Positivas = [2, 4, 6] -> media 4, desviacion poblacional sqrt(8/3)
        # CV2 = (sqrt(8/3) / 4)^2 = (8/3) / 16 = 1/6
        assert p["cv2"] == pytest.approx(1 / 6)

    def test_serie_regular_valores_calculados_a_mano(self):
        # Venta todos los dias, cantidades parecidas
        unidades = np.array([3, 4, 3, 5, 4, 3, 4, 5], dtype=float)
        p = sp.perfil_de_serie(unidades)

        assert p["proporcion_ceros"] == 0.0
        assert p["adi"] == 1.0  # 8 dias / 8 dias con demanda

        # media = 31/8 = 3.875 ; varianza poblacional = 4.875/8 = 0.609375
        # CV2 = 0.609375 / 3.875^2
        assert p["cv2"] == pytest.approx(0.609375 / (3.875**2))

    def test_serie_vacia(self):
        p = sp.perfil_de_serie(np.array([], dtype=float))
        assert p["dias_historial"] == 0
        assert p["proporcion_ceros"] == 1.0

    def test_serie_toda_en_ceros_no_divide_entre_cero(self):
        p = sp.perfil_de_serie(np.zeros(15))
        assert p["proporcion_ceros"] == 1.0
        assert p["adi"] == 15.0
        assert p["cv2"] == 0.0
        assert p["media_diaria"] == 0.0

    def test_una_sola_venta_no_tiene_dispersion(self):
        unidades = np.array([0, 0, 5, 0], dtype=float)
        p = sp.perfil_de_serie(unidades)
        assert p["adi"] == 4.0
        assert p["cv2"] == 0.0  # con una observacion no hay variabilidad medible

    def test_cv2_ignora_los_ceros(self):
        """El CV2 mide el tamano del pedido, no la serie con sus huecos."""
        densa = np.array([2, 4, 6], dtype=float)
        dispersa = np.array([2, 0, 0, 4, 0, 0, 6], dtype=float)
        assert sp.perfil_de_serie(densa)["cv2"] == pytest.approx(
            sp.perfil_de_serie(dispersa)["cv2"]
        )


class TestClasificar:
    @pytest.mark.parametrize(
        "adi,cv2,esperado",
        [
            (1.0, 0.10, "regular"),
            (1.0, 0.90, "erratica"),
            (3.0, 0.10, "intermitente"),
            (3.0, 0.90, "grumosa"),
        ],
    )
    def test_cuatro_cuadrantes(self, adi, cv2, esperado):
        assert sp.clasificar(adi, cv2) == esperado

    def test_los_cortes_pertenecen_al_cuadrante_superior(self):
        # Exactamente en el corte cuenta como intermitente/erratica, no como regular
        assert sp.clasificar(sp.CORTE_ADI, 0.1) == "intermitente"
        assert sp.clasificar(1.0, sp.CORTE_CV2) == "erratica"
        assert sp.clasificar(sp.CORTE_ADI - 0.01, 0.1) == "regular"


class TestEstrategiaPara:
    def test_historial_corto_manda_sobre_la_clasificacion(self):
        assert sp.estrategia_para("regular", sp.MIN_DIAS_PERFIL - 1) == "historial_insuficiente"

    def test_regular_va_a_modelo_directo(self):
        assert sp.estrategia_para("regular", 400) == "modelo_directo"

    @pytest.mark.parametrize("clase", ["intermitente", "grumosa"])
    def test_las_dispersas_no_van_a_modelo_directo(self, clase):
        assert sp.estrategia_para(clase, 400) == "agregar_semanal_o_metodo_intermitente"


class TestRejillaCompleta:
    def test_rellena_ceros_desde_la_primera_venta_de_cada_producto(self):
        """Un cero anterior al lanzamiento de un producto no es 'no hubo demanda'."""
        df = pd.DataFrame(
            {
                "fecha": pd.to_datetime(
                    ["2026-01-01", "2026-01-05", "2026-01-03"]
                ),
                "product_id": [1, 1, 2],
                "unidades": [2.0, 3.0, 7.0],
            }
        )

        rejilla = sp.rejilla_completa(df, fecha_fin=pd.Timestamp("2026-01-05"))

        # Producto 1 vendio primero el dia 1 -> 5 dias (1 al 5)
        p1 = rejilla[rejilla["product_id"] == 1].sort_values("fecha")
        assert len(p1) == 5
        assert list(p1["unidades"]) == [2.0, 0.0, 0.0, 0.0, 3.0]

        # Producto 2 aparecio el dia 3 -> solo 3 dias (3 al 5), NO 5
        p2 = rejilla[rejilla["product_id"] == 2].sort_values("fecha")
        assert len(p2) == 3
        assert p2["fecha"].min() == pd.Timestamp("2026-01-03")
        assert list(p2["unidades"]) == [7.0, 0.0, 0.0]

    def test_conserva_el_total_de_unidades(self):
        df = pd.DataFrame(
            {
                "fecha": pd.to_datetime(["2026-01-01", "2026-01-04"]),
                "product_id": [1, 1],
                "unidades": [5.0, 9.0],
            }
        )
        rejilla = sp.rejilla_completa(df, fecha_fin=pd.Timestamp("2026-01-04"))
        assert rejilla["unidades"].sum() == 14.0

    def test_dataframe_vacio(self):
        vacio = pd.DataFrame(columns=["fecha", "product_id", "unidades"])
        assert sp.rejilla_completa(vacio).empty


class TestResumir:
    def test_cuenta_por_clasificacion_y_calcula_porcentajes(self):
        perfiles = [
            {"clasificacion": "regular", "unidades_totales": 700.0},
            {"clasificacion": "erratica", "unidades_totales": 100.0},
            {"clasificacion": "intermitente", "unidades_totales": 150.0},
            {"clasificacion": "grumosa", "unidades_totales": 50.0},
        ]
        r = sp.resumir(perfiles)

        assert r["productos_con_ventas"] == 4
        assert r["regular"] == 1 and r["grumosa"] == 1
        # 2 de 4 series son dispersas
        assert r["pct_series_intermitentes"] == pytest.approx(50.0)
        # pero concentran poco volumen: 800 de 1000 unidades son modelables
        assert r["pct_volumen_modelable_directo"] == pytest.approx(80.0)

    def test_catalogo_vacio_no_divide_entre_cero(self):
        r = sp.resumir([])
        assert r["productos_con_ventas"] == 0
        assert r["pct_series_intermitentes"] == 0.0
