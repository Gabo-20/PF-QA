"""Pruebas de las lineas base y de la validacion de origen movil."""
import numpy as np
import pytest

from app.ml import baselines as b
from app.ml import evaluation as ev


class TestLineasBase:
    def test_naive_repite_el_ultimo_valor(self):
        y = np.array([1.0, 2, 3, 9])
        assert list(b.Naive().pronosticar(y, 3)) == [9.0, 9.0, 9.0]

    def test_naive_estacional_repite_el_ciclo(self):
        # Un ciclo semanal exacto
        y = np.array([1.0, 2, 3, 4, 5, 6, 7])
        pred = b.NaiveEstacional(periodo=7).pronosticar(y, 9)
        # Repite el ciclo y lo corta en h
        assert list(pred) == [1.0, 2, 3, 4, 5, 6, 7, 1, 2]

    def test_naive_estacional_sin_ciclo_completo_cae_a_naive(self):
        y = np.array([4.0, 5.0])
        assert list(b.NaiveEstacional(periodo=7).pronosticar(y, 2)) == [5.0, 5.0]

    def test_media_movil(self):
        y = np.array([1.0, 2, 3, 10, 20, 30, 40])
        # Media de las ultimas 3: (20+30+40)/3 = 30
        assert list(b.MediaMovil(ventana=3).pronosticar(y, 2)) == [30.0, 30.0]

    def test_media_movil_con_ventana_mayor_que_la_serie(self):
        y = np.array([2.0, 4.0])
        assert list(b.MediaMovil(ventana=50).pronosticar(y, 1)) == [3.0]

    def test_suavizamiento_con_alpha_uno_equivale_a_naive(self):
        """Con alfa = 1 el nivel es siempre la ultima observacion."""
        y = np.array([5.0, 10, 3, 8])
        pred = b.SuavizamientoExponencial(alpha=1.0).pronosticar(y, 2)
        assert list(pred) == [8.0, 8.0]

    def test_suavizamiento_con_alpha_bajo_se_acerca_al_promedio(self):
        y = np.concatenate([np.full(50, 10.0), np.full(50, 20.0)])
        suave = b.SuavizamientoExponencial(alpha=0.05).pronosticar(y, 1)[0]
        reactivo = b.SuavizamientoExponencial(alpha=0.9).pronosticar(y, 1)[0]
        # El reactivo sigue al nivel nuevo; el suave se queda atras
        assert reactivo > suave
        assert suave < 20.0

    def test_suavizamiento_elige_alpha_sin_mirar_el_futuro(self):
        """El ajuste de alfa solo usa la serie de entrenamiento que recibe."""
        y = np.array([10.0, 10, 10, 10, 10, 10, 10, 10])
        pred = b.SuavizamientoExponencial().pronosticar(y, 3)
        assert list(pred) == pytest.approx([10.0, 10.0, 10.0])

    def test_todas_devuelven_el_horizonte_pedido(self):
        y = np.asarray([10 + (i % 7) for i in range(120)], dtype=float)
        for modelo in [b.Naive(), b.NaiveEstacional(), b.MediaMovil(), b.SuavizamientoExponencial()]:
            assert len(modelo.pronosticar(y, 14)) == 14, modelo.nombre


class TestVentanasDisponibles:
    @pytest.mark.parametrize(
        "n,h,minimo,esperado",
        [
            (100, 7, 60, 5),   # (100-60)//7 = 5
            (74, 7, 60, 2),    # (74-60)//7 = 2
            (60, 7, 60, 0),    # justo en el minimo: no cabe ninguna
            (50, 7, 60, 0),    # menos que el minimo
        ],
    )
    def test_cuenta_ventanas(self, n, h, minimo, esperado):
        assert ev.ventanas_disponibles(n, h, minimo, maximo=5) == esperado

    def test_respeta_el_maximo(self):
        assert ev.ventanas_disponibles(10_000, 7, 60, maximo=5) == 5


class TestValidarOrigenMovil:
    def test_evalua_en_varias_ventanas(self):
        y = np.asarray([10 + (i % 7) for i in range(120)], dtype=float)
        r = ev.validar_origen_movil(y, lambda tr, h: b.NaiveEstacional().pronosticar(tr, h), h=7)

        assert r is not None
        assert r["n_ventanas"] == 5
        assert len(r["ventanas"]) == 5
        # Serie perfectamente estacional: el naive estacional acierta siempre
        assert r["promedio"]["mae"] == pytest.approx(0.0)

    def test_los_origenes_avanzan_y_el_entrenamiento_crece(self):
        y = np.asarray([10 + (i % 7) for i in range(120)], dtype=float)
        r = ev.validar_origen_movil(y, lambda tr, h: b.Naive().pronosticar(tr, h), h=7)
        tamanos = [v["n_entrenamiento"] for v in r["ventanas"]]
        assert tamanos == sorted(tamanos), "el origen debe avanzar hacia adelante"
        assert len(set(tamanos)) == len(tamanos), "no debe repetirse el mismo corte"

    def test_nunca_usa_datos_futuros(self):
        """El pronosticador solo recibe el pasado del corte."""
        y = np.arange(120, dtype=float)
        vistos = []

        def espia(entrenamiento, h):
            vistos.append(entrenamiento.max())
            return np.repeat(entrenamiento[-1], h)

        r = ev.validar_origen_movil(y, espia, h=7)
        for maximo_visto, ventana in zip(vistos, r["ventanas"]):
            # El maximo visto es el valor justo anterior al corte
            assert maximo_visto == ventana["corte"] - 1

    def test_historial_insuficiente_devuelve_none(self):
        assert ev.validar_origen_movil(np.arange(50, dtype=float), lambda tr, h: np.zeros(h), h=7) is None

    def test_un_candidato_que_falla_no_rompe_la_evaluacion(self):
        y = np.asarray([10 + (i % 7) for i in range(120)], dtype=float)

        def revienta(tr, h):
            raise RuntimeError("no converge")

        r = ev.validar_origen_movil(y, revienta, h=7)
        assert "error" in r and "no converge" in r["error"]


class TestCompararCandidatos:
    def test_ordena_por_mase_ascendente(self):
        y = np.asarray([10 + (i % 7) for i in range(150)], dtype=float)
        candidatos = {
            "naive_estacional": lambda tr, h: b.NaiveEstacional().pronosticar(tr, h),
            "naive": lambda tr, h: b.Naive().pronosticar(tr, h),
        }
        ranking = ev.comparar_candidatos(y, candidatos, h=7)

        assert [e["nombre"] for e in ranking][0] == "naive_estacional"
        assert all(e["evaluado"] for e in ranking)

    def test_registra_los_que_no_se_pudieron_evaluar(self):
        y = np.asarray([10 + (i % 7) for i in range(150)], dtype=float)

        def revienta(tr, h):
            raise ValueError("singular")

        ranking = ev.comparar_candidatos(y, {"malo": revienta}, h=7)
        assert ranking[0]["evaluado"] is False
        assert "singular" in ranking[0]["motivo"]


def _evaluacion(mases, sesgo=0.0):
    """Arma una evaluacion sintetica con los MASE dados por ventana."""
    return {
        "evaluado": True,
        "ventanas": [{"mase": v, "sesgo": sesgo} for v in mases],
        "promedio": {"mase": float(np.mean(mases)), "sesgo": sesgo},
    }


class TestDecidirPublicacion:
    def test_publica_si_mejora_lo_suficiente_y_es_consistente(self):
        modelo = _evaluacion([0.80, 0.82, 0.78, 0.81, 0.79])
        base = _evaluacion([1.00, 1.00, 1.00, 1.00, 1.00])
        d = ev.decidir_publicacion(modelo, base, volumen_medio=100.0)

        assert d["publicar"] is True
        assert d["mejora_pct"] == pytest.approx(20.0, abs=0.1)

    def test_rechaza_si_la_mejora_es_menor_al_10_por_ciento(self):
        modelo = _evaluacion([0.95] * 5)
        base = _evaluacion([1.00] * 5)
        d = ev.decidir_publicacion(modelo, base, volumen_medio=100.0)

        assert d["publicar"] is False
        assert "por debajo del minimo" in d["motivo"]

    def test_rechaza_un_modelo_peor_que_la_linea_base(self):
        modelo = _evaluacion([1.30] * 5)
        base = _evaluacion([1.00] * 5)
        assert ev.decidir_publicacion(modelo, base, volumen_medio=100.0)["publicar"] is False

    def test_rechaza_por_sesgo_excesivo_aunque_mejore(self):
        modelo = _evaluacion([0.50] * 5, sesgo=40.0)  # 40 % del volumen medio
        base = _evaluacion([1.00] * 5)
        d = ev.decidir_publicacion(modelo, base, volumen_medio=100.0)

        assert d["publicar"] is False
        assert "sesgo" in d["motivo"]

    def test_rechaza_si_gana_solo_en_la_mitad_de_las_ventanas(self):
        """El promedio puede engañar: dos ventanas excelentes y tres malas.

        MASE medio = 0.724, o sea 27.6 % de mejora, suficiente para pasar el
        umbral del 10 %. Pero solo le gana a la linea base en 2 de 5 ventanas,
        que es justo lo que el criterio de estabilidad debe atrapar.
        """
        modelo = _evaluacion([0.01, 0.01, 1.20, 1.20, 1.20])
        base = _evaluacion([1.00] * 5)
        d = ev.decidir_publicacion(modelo, base, volumen_medio=100.0)

        assert d["mejora_pct"] > 10, "el caso debe superar el umbral de mejora"
        assert d["consistencia"] == pytest.approx(0.4)
        assert d["publicar"] is False
        assert "inestable" in d["motivo"]

    def test_no_publica_si_el_modelo_no_pudo_evaluarse(self):
        d = ev.decidir_publicacion({"evaluado": False}, _evaluacion([1.0]), volumen_medio=100.0)
        assert d["publicar"] is False

    def test_el_umbral_se_resuelve_al_llamar_no_al_definir(self):
        """Si el umbral fuera un valor por defecto del argumento, ajustarlo en
        configuracion no tendria efecto: quedaria enlazado al importar."""
        modelo = _evaluacion([0.80] * 5)  # 20 % de mejora
        base = _evaluacion([1.00] * 5)

        original = ev.MEJORA_MINIMA
        try:
            ev.MEJORA_MINIMA = 0.99  # umbral imposible
            assert ev.decidir_publicacion(modelo, base, volumen_medio=100.0)["publicar"] is False
            ev.MEJORA_MINIMA = 0.05  # umbral laxo
            assert ev.decidir_publicacion(modelo, base, volumen_medio=100.0)["publicar"] is True
        finally:
            ev.MEJORA_MINIMA = original

    def test_umbral_explicito_tiene_prioridad(self):
        modelo = _evaluacion([0.80] * 5)
        base = _evaluacion([1.00] * 5)
        d = ev.decidir_publicacion(modelo, base, volumen_medio=100.0, mejora_minima=0.5)
        assert d["publicar"] is False

    def test_no_publica_si_el_mase_es_indefinido(self):
        modelo = {"evaluado": True, "ventanas": [], "promedio": {"mase": None, "sesgo": 0.0}}
        base = _evaluacion([1.0] * 5)
        d = ev.decidir_publicacion(modelo, base, volumen_medio=100.0)
        assert d["publicar"] is False
        assert "indefinido" in d["motivo"]


class TestConsistencia:
    def test_fraccion_de_ventanas_ganadas(self):
        modelo = _evaluacion([0.5, 0.5, 1.5, 1.5])
        base = _evaluacion([1.0, 1.0, 1.0, 1.0])
        assert ev.consistencia(modelo, base) == pytest.approx(0.5)

    def test_sin_ventanas_comparables(self):
        assert ev.consistencia({"ventanas": []}, {"ventanas": []}) is None
