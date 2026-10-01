"""Validacion temporal con origen movil y criterio de publicacion (cap. 2.5).

Antes se usaba un unico corte hold-out (85 % / 15 %). Con una sola ventana no se
puede afirmar que un modelo sea mejor: puede haber ganado por el periodo que le
toco. La tesis pide explicitamente varios origenes: *"En cada corte, el modelo se
entrena con el pasado y predice el horizonte siguiente. El origen avanza y el
proceso se repite"*.

El criterio de publicacion del cap. 2.5.1 se implementa aqui: un candidato solo
se publica si reduce al menos un 10 % el error escalado respecto al naive
estacional, no muestra sesgo inaceptable y gana en la mayoria de las ventanas.
Si nadie lo logra, gana la linea base.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

import numpy as np

from ..config import settings
from . import metrics

# Umbrales del cap. 2.5.1. Se leen de la configuracion porque la tesis los deja
# "sujetos a revision segun el tamano de la muestra" y deben acordarse con la
# empresa sin tocar codigo.
MEJORA_MINIMA = settings.MEJORA_MINIMA_PUBLICACION
# Sesgo maximo tolerado, como fraccion del volumen medio real del periodo.
SESGO_MAXIMO_RELATIVO = settings.SESGO_MAXIMO_RELATIVO
# Debe ganar en mas de la mitad de las ventanas para considerarse estable.
CONSISTENCIA_MINIMA = 0.5

MIN_ENTRENAMIENTO = 60
N_VENTANAS_POR_DEFECTO = 5


Pronosticador = Callable[[np.ndarray, int], np.ndarray]


def ventanas_disponibles(n_observaciones: int, h: int, min_entrenamiento: int = MIN_ENTRENAMIENTO,
                         maximo: int = N_VENTANAS_POR_DEFECTO) -> int:
    """Cuantas ventanas de origen movil caben sin bajar del minimo de entrenamiento."""
    if h <= 0:
        return 0
    caben = (n_observaciones - min_entrenamiento) // h
    return int(max(0, min(maximo, caben)))


def validar_origen_movil(
    y: np.ndarray,
    pronosticador: Pronosticador,
    h: int,
    n_ventanas: int = N_VENTANAS_POR_DEFECTO,
    periodo: int = metrics.PERIODO_ESTACIONAL,
    min_entrenamiento: int = MIN_ENTRENAMIENTO,
) -> Optional[dict]:
    """Evalua un pronosticador en varios origenes sucesivos.

    En cada ventana se reentrena solo con el pasado y se predice el horizonte
    siguiente, de modo que nunca se usa informacion futura.

    Devuelve None si la serie no da para ninguna ventana.
    """
    y = np.asarray(y, dtype=float)
    n_ventanas = min(n_ventanas, ventanas_disponibles(y.size, h, min_entrenamiento, n_ventanas))
    if n_ventanas <= 0:
        return None

    resultados = []
    for k in range(n_ventanas, 0, -1):
        corte = y.size - k * h
        entrenamiento = y[:corte]
        prueba = y[corte : corte + h]
        if prueba.size == 0:
            continue

        try:
            prediccion = np.asarray(pronosticador(entrenamiento, h), dtype=float)[: prueba.size]
        except Exception as exc:  # un candidato que no converge no invalida la comparacion
            return {"error": f"{type(exc).__name__}: {exc}", "ventanas": [], "promedio": {}}

        if prediccion.size != prueba.size:
            continue

        resultados.append(
            {
                "corte": int(corte),
                "n_entrenamiento": int(entrenamiento.size),
                **metrics.calcular_todas(prueba, prediccion, entrenamiento, periodo),
            }
        )

    if not resultados:
        return None

    return {
        "n_ventanas": len(resultados),
        "horizonte": h,
        "ventanas": resultados,
        "promedio": metrics.promediar(resultados),
    }


def comparar_candidatos(
    y: np.ndarray,
    candidatos: Dict[str, Pronosticador],
    h: int,
    n_ventanas: int = N_VENTANAS_POR_DEFECTO,
    periodo: int = metrics.PERIODO_ESTACIONAL,
) -> List[dict]:
    """Evalua todos los candidatos bajo el MISMO protocolo y los ordena por MASE.

    Los que fallan al ajustarse se conservan en la lista con su error, para que
    quede registro de que se intentaron (cap. 2.5.1: documentar el resultado).
    """
    evaluaciones = []
    for nombre, pronosticador in candidatos.items():
        resultado = validar_origen_movil(y, pronosticador, h, n_ventanas, periodo)
        if resultado is None:
            evaluaciones.append({"nombre": nombre, "evaluado": False, "motivo": "historial_insuficiente"})
            continue
        if resultado.get("error"):
            evaluaciones.append({"nombre": nombre, "evaluado": False, "motivo": resultado["error"]})
            continue
        evaluaciones.append({"nombre": nombre, "evaluado": True, **resultado})

    def clave_orden(e):
        if not e.get("evaluado"):
            return float("inf")
        mase = e["promedio"].get("mase")
        return mase if mase is not None else float("inf")

    evaluaciones.sort(key=clave_orden)
    return evaluaciones


def _mase_por_ventana(evaluacion: dict) -> List[Optional[float]]:
    return [v.get("mase") for v in evaluacion.get("ventanas", [])]


def consistencia(evaluacion_modelo: dict, evaluacion_baseline: dict) -> Optional[float]:
    """Fraccion de ventanas en las que el modelo le gana a la linea base."""
    a = _mase_por_ventana(evaluacion_modelo)
    b = _mase_por_ventana(evaluacion_baseline)
    pares = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if not pares:
        return None
    return sum(1 for x, y in pares if x < y) / len(pares)


def decidir_publicacion(
    evaluacion_modelo: dict,
    evaluacion_baseline: dict,
    volumen_medio: float,
    mejora_minima: Optional[float] = None,
    sesgo_maximo_relativo: Optional[float] = None,
    consistencia_minima: Optional[float] = None,
) -> dict:
    """Aplica el criterio del cap. 2.5.1.

    Devuelve la decision y el motivo, para que quede registrado tambien cuando
    la respuesta es que no se publica.

    Los umbrales se resuelven en tiempo de llamada, no como valores por defecto
    del argumento: si se enlazaran al definir la funcion, ajustar el umbral en
    configuracion no tendria ningun efecto.
    """
    mejora_minima = MEJORA_MINIMA if mejora_minima is None else mejora_minima
    sesgo_maximo_relativo = (
        SESGO_MAXIMO_RELATIVO if sesgo_maximo_relativo is None else sesgo_maximo_relativo
    )
    consistencia_minima = (
        CONSISTENCIA_MINIMA if consistencia_minima is None else consistencia_minima
    )
    if not evaluacion_modelo.get("evaluado"):
        return {"publicar": False, "motivo": "el modelo no pudo evaluarse", "mejora_pct": None}

    mase_modelo = evaluacion_modelo["promedio"].get("mase")
    mase_base = evaluacion_baseline.get("promedio", {}).get("mase") if evaluacion_baseline else None

    if mase_modelo is None or mase_base is None or mase_base == 0:
        return {"publicar": False, "motivo": "MASE indefinido: no hay comparacion posible", "mejora_pct": None}

    mejora = (mase_base - mase_modelo) / mase_base
    sesgo_modelo = evaluacion_modelo["promedio"].get("sesgo")
    sesgo_relativo = abs(sesgo_modelo) / volumen_medio if sesgo_modelo is not None and volumen_medio else None
    estabilidad = consistencia(evaluacion_modelo, evaluacion_baseline)

    detalle = {
        "mase_modelo": round(mase_modelo, 4),
        "mase_baseline": round(mase_base, 4),
        "mejora_pct": round(mejora * 100, 2),
        "sesgo_relativo_pct": round(sesgo_relativo * 100, 2) if sesgo_relativo is not None else None,
        "consistencia": round(estabilidad, 2) if estabilidad is not None else None,
    }

    if mejora < mejora_minima:
        return {
            "publicar": False,
            "motivo": f"mejora de {detalle['mejora_pct']}% por debajo del minimo de {mejora_minima*100:.0f}%",
            **detalle,
        }
    if sesgo_relativo is not None and sesgo_relativo > sesgo_maximo_relativo:
        return {
            "publicar": False,
            "motivo": f"sesgo relativo de {detalle['sesgo_relativo_pct']}% supera el maximo tolerado",
            **detalle,
        }
    if estabilidad is not None and estabilidad <= consistencia_minima:
        return {
            "publicar": False,
            "motivo": f"solo gana en {detalle['consistencia']} de las ventanas: desempeno inestable",
            **detalle,
        }

    return {"publicar": True, "motivo": "supera la linea base de forma consistente", **detalle}
