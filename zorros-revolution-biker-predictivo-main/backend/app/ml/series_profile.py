"""Perfilamiento de las series de demanda por producto.

La tesis (cap. 2.2.3) exige calcular, ANTES de entrenar, la proporcion de ceros,
el intervalo promedio entre demandas y la variabilidad de las cantidades, para
decidir si una serie admite un modelo directo o necesita tratamiento especial.

Este modulo trabaja sobre **unidades por producto y dia**, no sobre el total
diario en quetzales que consume hoy `forecasting.py`. Son dos cosas distintas:
el ingreso mezcla el efecto del precio con el de la demanda, mientras que las
unidades son la senal fisica que interesa para decidir cuanto comprar
(cap. 2.1 de la tesis).

Clasificacion de Syntetos-Boylan-Croston, con los cortes habituales
ADI = 1.32 y CV2 = 0.49:

                    CV2 < 0.49        CV2 >= 0.49
    ADI < 1.32      regular           erratica
    ADI >= 1.32     intermitente      grumosa
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models

# Cortes de la clasificacion de Syntetos-Boylan-Croston.
CORTE_ADI = 1.32
CORTE_CV2 = 0.49

# Por debajo de este historial el perfil es demasiado inestable para confiar en el.
MIN_DIAS_PERFIL = 30


def ventas_por_producto_dia(db: Session) -> pd.DataFrame:
    """Unidades vendidas por producto y dia, tal como estan en la base.

    No rellena los dias sin venta: de eso se encarga `rejilla_completa`.
    """
    filas = (
        db.query(
            func.date(models.Sale.fecha_hora).label("fecha"),
            models.SaleItem.product_id.label("product_id"),
            func.sum(models.SaleItem.cantidad).label("unidades"),
        )
        .join(models.Sale, models.SaleItem.sale_id == models.Sale.id)
        .group_by(func.date(models.Sale.fecha_hora), models.SaleItem.product_id)
        .all()
    )
    if not filas:
        return pd.DataFrame(columns=["fecha", "product_id", "unidades"])

    df = pd.DataFrame(filas, columns=["fecha", "product_id", "unidades"])
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["unidades"] = df["unidades"].astype(float)
    return df


def rejilla_completa(df: pd.DataFrame, fecha_fin: Optional[pd.Timestamp] = None) -> pd.DataFrame:
    """Rellena con cero los dias sin venta de cada producto.

    El relleno arranca en la PRIMERA venta de cada producto, no en la fecha mas
    antigua del catalogo: un cero anterior al lanzamiento de un articulo no
    significa "no hubo demanda", significa que el producto todavia no existia, y
    contarlo hundiria artificialmente su media y su proporcion de ceros.
    """
    if df.empty:
        return df

    fin = fecha_fin if fecha_fin is not None else df["fecha"].max()
    partes = []
    for product_id, grupo in df.groupby("product_id"):
        indice = pd.date_range(grupo["fecha"].min(), fin, freq="D")
        serie = grupo.set_index("fecha")["unidades"].reindex(indice, fill_value=0.0)
        partes.append(
            pd.DataFrame({"fecha": indice, "product_id": product_id, "unidades": serie.to_numpy()})
        )

    return pd.concat(partes, ignore_index=True)


def clasificar(adi: float, cv2: float) -> str:
    """Cuadrante de Syntetos-Boylan-Croston."""
    if adi < CORTE_ADI:
        return "regular" if cv2 < CORTE_CV2 else "erratica"
    return "intermitente" if cv2 < CORTE_CV2 else "grumosa"


def estrategia_para(clasificacion: str, dias_historial: int) -> str:
    """Como conviene pronosticar una serie segun su perfil."""
    if dias_historial < MIN_DIAS_PERFIL:
        return "historial_insuficiente"
    if clasificacion == "regular":
        return "modelo_directo"
    if clasificacion == "erratica":
        return "modelo_directo_con_intervalos_amplios"
    # Intermitente y grumosa: los ceros dominan y un regresor sobre la serie
    # diaria aprende a predecir cero. Conviene agregar temporalmente o usar un
    # metodo especifico de demanda intermitente (Croston / SBA).
    return "agregar_semanal_o_metodo_intermitente"


def perfil_de_serie(unidades: np.ndarray) -> dict:
    """Estadisticos de intermitencia de una serie diaria de unidades.

    - proporcion_ceros: fraccion de dias sin venta.
    - adi: Average Demand Interval, dias por cada dia con demanda.
    - cv2: cuadrado del coeficiente de variacion de las cantidades POSITIVAS
      (la variabilidad del tamano del pedido, no la de la serie con ceros).
    """
    n = int(len(unidades))
    if n == 0:
        return {
            "dias_historial": 0,
            "unidades_totales": 0.0,
            "media_diaria": 0.0,
            "proporcion_ceros": 1.0,
            "adi": 0.0,
            "cv2": 0.0,
        }

    positivas = unidades[unidades > 0]
    n_positivas = int(len(positivas))

    if n_positivas == 0:
        # Sin ninguna venta no hay demanda que caracterizar.
        return {
            "dias_historial": n,
            "unidades_totales": 0.0,
            "media_diaria": 0.0,
            "proporcion_ceros": 1.0,
            "adi": float(n),
            "cv2": 0.0,
        }

    media_positivas = float(positivas.mean())
    # Con una sola observacion positiva no hay dispersion medible: cv2 = 0.
    if n_positivas > 1 and media_positivas > 0:
        cv2 = float((positivas.std(ddof=0) / media_positivas) ** 2)
    else:
        cv2 = 0.0

    return {
        "dias_historial": n,
        "unidades_totales": float(unidades.sum()),
        "media_diaria": float(unidades.mean()),
        "proporcion_ceros": float((n - n_positivas) / n),
        "adi": float(n / n_positivas),
        "cv2": cv2,
    }


def perfilar_catalogo(db: Session) -> List[dict]:
    """Perfil de cada producto con ventas, ordenado por volumen descendente."""
    df = rejilla_completa(ventas_por_producto_dia(db))
    if df.empty:
        return []

    productos = {p.id: p for p in db.query(models.Product).all()}

    perfiles = []
    for product_id, grupo in df.groupby("product_id"):
        producto = productos.get(int(product_id))
        if producto is None:
            continue

        metricas = perfil_de_serie(grupo["unidades"].to_numpy())
        clasificacion = clasificar(metricas["adi"], metricas["cv2"])

        perfiles.append(
            {
                "product_id": int(product_id),
                "sku": producto.sku,
                "nombre": producto.nombre,
                "categoria": producto.categoria,
                "clasificacion": clasificacion,
                "estrategia_sugerida": estrategia_para(clasificacion, metricas["dias_historial"]),
                **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in metricas.items()},
            }
        )

    perfiles.sort(key=lambda p: p["unidades_totales"], reverse=True)
    return perfiles


def resumir(perfiles: List[dict]) -> dict:
    """Conteo por clasificacion y cobertura, para leer el catalogo de un vistazo."""
    total = len(perfiles)
    conteo = {"regular": 0, "erratica": 0, "intermitente": 0, "grumosa": 0}
    for p in perfiles:
        conteo[p["clasificacion"]] = conteo.get(p["clasificacion"], 0) + 1

    # Que parte del volumen vendido esta en series que un modelo directo maneja bien.
    unidades_total = sum(p["unidades_totales"] for p in perfiles) or 1.0
    unidades_modelables = sum(
        p["unidades_totales"] for p in perfiles if p["clasificacion"] in ("regular", "erratica")
    )

    return {
        "productos_con_ventas": total,
        "regular": conteo["regular"],
        "erratica": conteo["erratica"],
        "intermitente": conteo["intermitente"],
        "grumosa": conteo["grumosa"],
        "pct_series_intermitentes": round(
            (conteo["intermitente"] + conteo["grumosa"]) / total * 100, 2
        )
        if total
        else 0.0,
        "pct_volumen_modelable_directo": round(unidades_modelables / unidades_total * 100, 2),
    }
