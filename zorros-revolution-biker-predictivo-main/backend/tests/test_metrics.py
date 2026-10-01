"""Pruebas de las metricas de pronostico.

Todos los valores esperados estan calculados a mano. Es deliberado: si se
comparan contra lo que devuelve el propio codigo, la prueba pasa igual cuando la
formula esta mal, que es exactamente lo que ocurria con el "MASE" anterior.
"""
import numpy as np
import pytest

from app.ml import metrics as m

# Caso base compartido:
#   real      = [10, 20, 30]
#   prediccion= [12, 18, 33]
#   errores (pred - real) = [+2, -2, +3]  ->  absolutos [2, 2, 3]
REAL = np.array([10.0, 20.0, 30.0])
PRED = np.array([12.0, 18.0, 33.0])


class TestMetricasPuntuales:
    def test_mae(self):
        assert m.mae(REAL, PRED) == pytest.approx(7 / 3)

    def test_rmse(self):
        # sqrt((2^2 + 2^2 + 3^2) / 3) = sqrt(17/3)
        assert m.rmse(REAL, PRED) == pytest.approx(np.sqrt(17 / 3))

    def test_wape(self):
        # suma de errores absolutos 7, volumen real 60 -> 11.666...%
        assert m.wape(REAL, PRED) == pytest.approx(7 / 60 * 100)

    def test_sesgo_positivo_es_sobreestimacion(self):
        # (+2 - 2 + 3) / 3 = 1
        assert m.sesgo(REAL, PRED) == pytest.approx(1.0)

    def test_sesgo_negativo_es_subestimacion(self):
        assert m.sesgo(REAL, REAL - 5) == pytest.approx(-5.0)

    def test_smape(self):
        # denominadores (|real|+|pred|)/2 = 11, 19, 31.5
        esperado = np.mean([2 / 11, 2 / 19, 3 / 31.5]) * 100
        assert m.smape(REAL, PRED) == pytest.approx(esperado)


class TestMase:
    def test_se_escala_con_el_naive_IN_SAMPLE(self):
        """El denominador sale del ENTRENAMIENTO, no del conjunto de prueba."""
        # Entrenamiento: 9 valores, periodo 7
        #   y[7:]  = [24, 26]
        #   y[:-7] = [10, 12]
        #   |diff| = [14, 14]  ->  escala = 14
        entrenamiento = np.array([10.0, 12, 14, 16, 18, 20, 22, 24, 26])
        assert m.escala_mase(entrenamiento, periodo=7) == pytest.approx(14.0)

        # MASE = MAE / escala = (7/3) / 14
        assert m.mase(REAL, PRED, entrenamiento, periodo=7) == pytest.approx((7 / 3) / 14)

    def test_el_conjunto_de_prueba_no_afecta_la_escala(self):
        """Regresion: la version anterior escalaba con el naive out-of-sample."""
        entrenamiento = np.array([10.0, 12, 14, 16, 18, 20, 22, 24, 26])
        escala = m.escala_mase(entrenamiento, periodo=7)

        # Cambiar el conjunto de prueba no puede mover la escala
        otro_real = np.array([100.0, 200.0, 300.0])
        assert m.escala_mase(entrenamiento, periodo=7) == escala
        assert m.mase(otro_real, otro_real, entrenamiento, periodo=7) == 0.0

    def test_menor_que_uno_significa_mejor_que_el_naive(self):
        entrenamiento = np.array([10.0, 12, 14, 16, 18, 20, 22, 24, 26])  # escala 14
        real = np.array([50.0, 50.0])
        casi_perfecto = np.array([51.0, 49.0])  # MAE = 1
        assert m.mase(real, casi_perfecto, entrenamiento, periodo=7) == pytest.approx(1 / 14)
        assert m.mase(real, casi_perfecto, entrenamiento, periodo=7) < 1

    def test_historial_menor_que_el_periodo_no_tiene_escala(self):
        assert m.escala_mase(np.array([1.0, 2, 3]), periodo=7) is None
        assert m.mase(REAL, PRED, np.array([1.0, 2, 3]), periodo=7) is None

    def test_serie_constante_no_tiene_escala(self):
        """Escala cero: MASE indefinido, NO cero."""
        constante = np.full(20, 5.0)
        assert m.escala_mase(constante, periodo=7) is None
        assert m.mase(REAL, PRED, constante, periodo=7) is None


class TestIndefinidasDevuelvenNone:
    """El bug anterior: devolver 0.0 hacia parecer que el error era perfecto."""

    def test_wape_sin_volumen_es_indefinido_no_cero(self):
        resultado = m.wape(np.zeros(5), np.array([1.0, 2, 3, 4, 5]))
        assert resultado is None
        assert resultado != 0.0

    def test_series_vacias(self):
        vacio = np.array([])
        assert m.mae(vacio, vacio) is None
        assert m.rmse(vacio, vacio) is None
        assert m.wape(vacio, vacio) is None
        assert m.smape(vacio, vacio) is None
        assert m.sesgo(vacio, vacio) is None

    def test_smape_todo_cero(self):
        assert m.smape(np.zeros(3), np.zeros(3)) is None


class TestCalcularTodas:
    def test_devuelve_las_seis_metricas(self):
        entrenamiento = np.array([10.0, 12, 14, 16, 18, 20, 22, 24, 26])
        r = m.calcular_todas(REAL, PRED, entrenamiento)
        assert set(r) == {"mae", "rmse", "wape", "smape", "sesgo", "mase"}
        assert r["mae"] == pytest.approx(7 / 3)


class TestPromediar:
    def test_promedia_ignorando_indefinidas(self):
        r = m.promediar([{"mae": 10.0}, {"mae": None}, {"mae": 20.0}])
        assert r["mae"] == pytest.approx(15.0)

    def test_si_todas_son_indefinidas_el_promedio_tambien(self):
        r = m.promediar([{"mae": None}, {"mae": None}])
        assert r["mae"] is None

    def test_lista_vacia(self):
        assert m.promediar([]) == {}

    def test_solo_promedia_metricas_no_metadatos_de_la_ventana(self):
        """El corte y el tamano del entrenamiento no son metricas de error."""
        ventanas = [
            {"corte": 100, "n_entrenamiento": 100, "mae": 10.0, "rmse": 1.0,
             "wape": 1.0, "smape": 1.0, "sesgo": 1.0, "mase": 1.0},
            {"corte": 130, "n_entrenamiento": 130, "mae": 20.0, "rmse": 1.0,
             "wape": 1.0, "smape": 1.0, "sesgo": 1.0, "mase": 1.0},
        ]
        r = m.promediar(ventanas)

        assert set(r) == set(m.CLAVES_METRICAS)
        assert "corte" not in r and "n_entrenamiento" not in r
        assert r["mae"] == pytest.approx(15.0)
