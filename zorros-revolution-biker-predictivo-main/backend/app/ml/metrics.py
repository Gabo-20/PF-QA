"""Metricas de evaluacion de pronosticos (cap. 2.5 de la tesis).

Dos criterios de diseno, ambos correcciones a como estaba antes:

1. **Cuando una metrica no esta definida se devuelve None, nunca 0.0.**
   El codigo anterior devolvia 0.0 si el denominador era cero, de modo que una
   serie de prueba vacia reportaba "WAPE = 0 %", es decir error perfecto, y de
   ahi salia una "confianza del modelo" del 100 %. Un error de cero y un error
   indefinido son cosas distintas y no pueden colapsarse.

2. **MASE se escala con el error in-sample, no con el out-of-sample.**
   Hyndman y Koehler (2006), la referencia que cita la propia tesis, definen
   MASE como el MAE del modelo dividido entre el MAE del naive estacional
   calculado sobre el conjunto de ENTRENAMIENTO. Escalarlo con el naive sobre
   el mismo conjunto de prueba da RelMAE, que es otra metrica: no es comparable
   con la literatura ni entre series de escalas distintas.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

# Estacionalidad semanal para datos diarios.
PERIODO_ESTACIONAL = 7

# Las metricas que produce `calcular_todas`. Sirve para no promediar por error
# campos que acompanan a una ventana pero no son metricas (el corte, el tamano
# del entrenamiento), que quedarian reportados como si lo fueran.
CLAVES_METRICAS = ("mae", "rmse", "wape", "smape", "sesgo", "mase")


def _como_array(x) -> np.ndarray:
    return np.asarray(x, dtype=float).ravel()


def mae(y_true, y_pred) -> Optional[float]:
    """Error absoluto medio, en las unidades de la serie."""
    y_true, y_pred = _como_array(y_true), _como_array(y_pred)
    if y_true.size == 0:
        return None
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true, y_pred) -> Optional[float]:
    """Raiz del error cuadratico medio. Penaliza mas los errores grandes."""
    y_true, y_pred = _como_array(y_true), _como_array(y_pred)
    if y_true.size == 0:
        return None
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def wape(y_true, y_pred) -> Optional[float]:
    """Error absoluto total relativo al volumen, en porcentaje.

    Indefinido si no hubo volumen en el periodo (no es "error cero").
    """
    y_true, y_pred = _como_array(y_true), _como_array(y_pred)
    if y_true.size == 0:
        return None
    denominador = float(np.sum(np.abs(y_true)))
    if denominador == 0:
        return None
    return float(np.sum(np.abs(y_true - y_pred)) / denominador * 100)


def smape(y_true, y_pred) -> Optional[float]:
    """sMAPE simetrico. Inestable cerca de cero, por eso es complementaria."""
    y_true, y_pred = _como_array(y_true), _como_array(y_pred)
    if y_true.size == 0:
        return None
    denominador = (np.abs(y_true) + np.abs(y_pred)) / 2
    validos = denominador > 0
    if not validos.any():
        return None
    return float(
        np.mean(np.abs(y_true[validos] - y_pred[validos]) / denominador[validos]) * 100
    )


def sesgo(y_true, y_pred) -> Optional[float]:
    """Error medio con signo: positivo = el modelo sobreestima.

    La tesis lo exige como criterio de publicacion (cap. 2.5.1: "no presenta
    sesgo inaceptable"). No mide magnitud total del error, solo su direccion.
    """
    y_true, y_pred = _como_array(y_true), _como_array(y_pred)
    if y_true.size == 0:
        return None
    return float(np.mean(y_pred - y_true))


def escala_mase(y_entrenamiento, periodo: int = PERIODO_ESTACIONAL) -> Optional[float]:
    """MAE del naive estacional sobre el conjunto de entrenamiento.

    Es el denominador de MASE. Devuelve None si no hay historial suficiente para
    calcularlo o si la serie es constante (escala cero), casos en los que MASE
    no esta definido.
    """
    y = _como_array(y_entrenamiento)
    if y.size <= periodo:
        return None
    escala = float(np.mean(np.abs(y[periodo:] - y[:-periodo])))
    return escala if escala > 0 else None


def mase(y_true, y_pred, y_entrenamiento, periodo: int = PERIODO_ESTACIONAL) -> Optional[float]:
    """MASE de Hyndman y Koehler (2006).

    Menor que 1 significa que el modelo le gana al naive estacional.
    """
    error = mae(y_true, y_pred)
    escala = escala_mase(y_entrenamiento, periodo)
    if error is None or escala is None:
        return None
    return float(error / escala)


def calcular_todas(y_true, y_pred, y_entrenamiento, periodo: int = PERIODO_ESTACIONAL) -> dict:
    """Todas las metricas del cap. 2.5 de una sola pasada."""
    return {
        "mae": mae(y_true, y_pred),
        "rmse": rmse(y_true, y_pred),
        "wape": wape(y_true, y_pred),
        "smape": smape(y_true, y_pred),
        "sesgo": sesgo(y_true, y_pred),
        "mase": mase(y_true, y_pred, y_entrenamiento, periodo),
    }


def promediar(lista_metricas: list[dict]) -> dict:
    """Promedia las metricas entre ventanas ignorando las indefinidas.

    Solo promedia las claves de `CLAVES_METRICAS`: cualquier otro campo que
    acompane a la ventana (el corte, el tamano del entrenamiento) se descarta,
    porque promediarlo lo presentaria como una metrica de error.

    Si una metrica quedo indefinida en TODAS las ventanas, el promedio tambien
    es None: no se inventa un cero.
    """
    if not lista_metricas:
        return {}
    promedio = {}
    for clave in CLAVES_METRICAS:
        valores = [m[clave] for m in lista_metricas if m.get(clave) is not None]
        promedio[clave] = float(np.mean(valores)) if valores else None
    return promedio
