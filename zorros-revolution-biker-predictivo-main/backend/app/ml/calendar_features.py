"""Features de calendario para capturar la estacionalidad de ventas en Guatemala.

Temporadas consideradas:
  - Diciembre: aguinaldo + temporada navideña, pico de gasto del año.
  - Bono 14: bonificación anual de ley pagada en la primera quincena de julio.
  - Caravana del Zorro: evento anual de motociclismo (segunda quincena de febrero),
    asociado directamente a la marca Zorros Revolution Biker.
"""
import math
from datetime import date, datetime
from typing import Union

DateLike = Union[date, datetime]


def _as_date(d: DateLike) -> date:
    return d.date() if isinstance(d, datetime) else d


def es_temporada_diciembre(d: DateLike) -> bool:
    return _as_date(d).month == 12


def es_semana_bono14(d: DateLike) -> bool:
    d = _as_date(d)
    return d.month == 7 and d.day <= 15


def es_caravana_del_zorro(d: DateLike) -> bool:
    d = _as_date(d)
    return d.month == 2 and d.day >= 14


def _dias_hasta_ventana(d: DateLike, mes_inicio: int, dia_inicio: int, en_curso) -> int:
    """Días que faltan para que inicie la ventana del evento.

    Devuelve 0 mientras el evento está en curso: de lo contrario el sistema dejaría
    de anticipar un evento justo durante el evento (el 15 de diciembre faltarían
    351 días para "el próximo diciembre"), y el refuerzo de reabastecimiento nunca
    se aplicaría en plena temporada.
    """
    d = _as_date(d)
    if en_curso(d):
        return 0
    objetivo = date(d.year, mes_inicio, dia_inicio)
    if d > objetivo:
        objetivo = date(d.year + 1, mes_inicio, dia_inicio)
    return (objetivo - d).days


def dias_hasta_diciembre(d: DateLike) -> int:
    return _dias_hasta_ventana(d, 12, 1, es_temporada_diciembre)


def dias_hasta_bono14(d: DateLike) -> int:
    return _dias_hasta_ventana(d, 7, 1, es_semana_bono14)


def dias_hasta_caravana_zorro(d: DateLike) -> int:
    return _dias_hasta_ventana(d, 2, 14, es_caravana_del_zorro)


def proximo_evento(d: DateLike):
    """Devuelve (nombre_evento, dias_restantes) del evento estacional más cercano."""
    eventos = [
        ("Diciembre / Aguinaldo", dias_hasta_diciembre(d)),
        ("Bono 14 (julio)", dias_hasta_bono14(d)),
        ("Caravana del Zorro (febrero)", dias_hasta_caravana_zorro(d)),
    ]
    return min(eventos, key=lambda x: x[1])


def features_dict(d: DateLike) -> dict:
    d = _as_date(d)
    return {
        "dia_semana": d.weekday(),
        "es_fin_de_semana": 1 if d.weekday() >= 5 else 0,
        "mes": d.month,
        "mes_sin": math.sin(2 * math.pi * d.month / 12),
        "mes_cos": math.cos(2 * math.pi * d.month / 12),
        "dia_mes": d.day,
        "is_diciembre": int(es_temporada_diciembre(d)),
        "is_semana_bono14": int(es_semana_bono14(d)),
        "is_caravana_zorro": int(es_caravana_del_zorro(d)),
    }
