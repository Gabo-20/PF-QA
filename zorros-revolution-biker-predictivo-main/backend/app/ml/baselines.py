"""Modelos de referencia para el pronostico (cap. 2.2.2 de la tesis).

La tesis es explicita: *"un modelo de inteligencia artificial solo agrega valor
si los supera de forma consistente"*. Antes solo existia el naive estacional, y
ni siquiera como candidato comparable sino como una cuenta suelta dentro del
entrenamiento.

Todas las clases comparten la misma interfaz que el modelo de IA:

    pronosticar(y, h) -> np.ndarray con h valores

`y` es la serie de entrenamiento (solo el pasado) y `h` el horizonte. Ninguna
mira el futuro, de modo que las cinco se pueden evaluar bajo el mismo protocolo
de origen movil.

Naive, naive estacional, media movil y suavizamiento exponencial se implementan
aqui porque son verificables a mano en una prueba. Holt-Winters y ARIMA se
delegan a statsmodels: hacerlos a mano arriesga un error sutil que haria parecer
mejor al modelo de IA, que es justo el sesgo contra el que la tesis advierte.
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np

PERIODO_ESTACIONAL = 7


class LineaBase:
    """Interfaz comun. `nombre` se usa para registrar el candidato ganador."""

    nombre: str = "base"

    def pronosticar(self, y: np.ndarray, h: int) -> np.ndarray:
        raise NotImplementedError


class Naive(LineaBase):
    """Repite el ultimo valor observado."""

    nombre = "naive"

    def pronosticar(self, y: np.ndarray, h: int) -> np.ndarray:
        y = np.asarray(y, dtype=float)
        return np.repeat(y[-1], h)


class NaiveEstacional(LineaBase):
    """Repite el ciclo anterior: el mismo dia de la semana pasada."""

    nombre = "naive_estacional"

    def __init__(self, periodo: int = PERIODO_ESTACIONAL):
        self.periodo = periodo

    def pronosticar(self, y: np.ndarray, h: int) -> np.ndarray:
        y = np.asarray(y, dtype=float)
        if y.size < self.periodo:
            return np.repeat(y[-1], h)
        ultimo_ciclo = y[-self.periodo :]
        repeticiones = int(np.ceil(h / self.periodo))
        return np.tile(ultimo_ciclo, repeticiones)[:h]


class MediaMovil(LineaBase):
    """Promedio de las ultimas `ventana` observaciones, plano hacia adelante."""

    nombre = "media_movil"

    def __init__(self, ventana: int = 7):
        self.ventana = ventana

    def pronosticar(self, y: np.ndarray, h: int) -> np.ndarray:
        y = np.asarray(y, dtype=float)
        ventana = min(self.ventana, y.size)
        return np.repeat(float(np.mean(y[-ventana:])), h)


class SuavizamientoExponencial(LineaBase):
    """Suavizamiento exponencial simple, con alfa ajustado por rejilla.

    El nivel se actualiza como  l_t = alfa*y_t + (1-alfa)*l_{t-1}  y el
    pronostico es plano en el ultimo nivel. Alfa se elige minimizando el error
    cuadratico dentro de la muestra de entrenamiento (nunca con datos futuros).
    """

    nombre = "suavizamiento_exponencial"

    def __init__(self, alpha: Optional[float] = None):
        self.alpha = alpha

    @staticmethod
    def _nivel_final(y: np.ndarray, alpha: float) -> float:
        nivel = float(y[0])
        for valor in y[1:]:
            nivel = alpha * float(valor) + (1 - alpha) * nivel
        return nivel

    @staticmethod
    def _sse(y: np.ndarray, alpha: float) -> float:
        """Suma de errores al cuadrado de las predicciones a un paso."""
        nivel = float(y[0])
        total = 0.0
        for valor in y[1:]:
            total += (float(valor) - nivel) ** 2
            nivel = alpha * float(valor) + (1 - alpha) * nivel
        return total

    def _mejor_alpha(self, y: np.ndarray) -> float:
        candidatos = np.arange(0.05, 1.0, 0.05)
        return float(min(candidatos, key=lambda a: self._sse(y, a)))

    def pronosticar(self, y: np.ndarray, h: int) -> np.ndarray:
        y = np.asarray(y, dtype=float)
        if y.size == 1:
            return np.repeat(y[-1], h)
        alpha = self.alpha if self.alpha is not None else self._mejor_alpha(y)
        return np.repeat(self._nivel_final(y, alpha), h)


class HoltWinters(LineaBase):
    """Holt-Winters aditivo con estacionalidad semanal (statsmodels)."""

    nombre = "holt_winters"

    def __init__(self, periodo: int = PERIODO_ESTACIONAL):
        self.periodo = periodo

    def pronosticar(self, y: np.ndarray, h: int) -> np.ndarray:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing

        y = np.asarray(y, dtype=float)
        modelo = ExponentialSmoothing(
            y, trend="add", seasonal="add", seasonal_periods=self.periodo,
            initialization_method="estimated",
        ).fit(optimized=True)
        return np.asarray(modelo.forecast(h), dtype=float)


class Arima(LineaBase):
    """ARIMA con orden fijo (statsmodels).

    Se usa un orden fijo y no una busqueda automatica porque el VPS tiene un
    solo nucleo y la validacion de origen movil ya reajusta el modelo en cada
    ventana.
    """

    nombre = "arima"

    def __init__(self, orden: tuple = (1, 1, 1)):
        self.orden = orden

    def pronosticar(self, y: np.ndarray, h: int) -> np.ndarray:
        from statsmodels.tsa.arima.model import ARIMA

        y = np.asarray(y, dtype=float)
        modelo = ARIMA(y, order=self.orden).fit()
        return np.asarray(modelo.forecast(h), dtype=float)


def catalogo_por_defecto() -> List[LineaBase]:
    """Las cinco referencias que nombra el cap. 2.2.2."""
    return [
        Naive(),
        NaiveEstacional(),
        MediaMovil(ventana=7),
        SuavizamientoExponencial(),
        HoltWinters(),
        Arima(),
    ]
