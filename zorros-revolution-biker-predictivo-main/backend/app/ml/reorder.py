"""Cálculo de punto de reorden y recomendaciones de reabastecimiento.

Los productos se importan de China, por lo que el tiempo de envío (lead time)
es el factor crítico para evitar desabastecimiento: el punto de reorden se
calcula como la demanda esperada durante ese tiempo de envío más un margen de
seguridad, y se anticipa cuando un evento de alta demanda en Guatemala
(diciembre, Bono 14, Caravana del Zorro) cae dentro de esa ventana.
"""
from datetime import datetime, timedelta
from typing import List

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from . import calendar_features as cf


def _demanda_diaria_promedio(db: Session, product_id: int, dias: int = 60) -> float:
    desde = datetime.utcnow() - timedelta(days=dias)
    total = (
        db.query(func.coalesce(func.sum(models.SaleItem.cantidad), 0))
        .join(models.Sale)
        .filter(models.SaleItem.product_id == product_id, models.Sale.fecha_hora >= desde)
        .scalar()
    ) or 0
    return total / dias


def _pedidos_en_transito(db: Session, product_id: int) -> int:
    total = (
        db.query(func.coalesce(func.sum(models.PurchaseOrder.cantidad), 0))
        .filter(
            models.PurchaseOrder.product_id == product_id,
            models.PurchaseOrder.estado.in_([models.EstadoPedido.pendiente, models.EstadoPedido.en_transito]),
        )
        .scalar()
    ) or 0
    return total


def generar_recomendaciones(db: Session) -> List[schemas.RecommendationOut]:
    hoy = datetime.utcnow()
    evento_nombre, dias_evento = cf.proximo_evento(hoy)

    recomendaciones: List[schemas.RecommendationOut] = []
    productos = db.query(models.Product).filter(models.Product.activo == True).all()  # noqa: E712

    for producto in productos:
        demanda_diaria = _demanda_diaria_promedio(db, producto.id)

        # Si el próximo evento de alta demanda cae dentro de la ventana de envío desde
        # China, se anticipa el pedido subiendo la demanda diaria esperada.
        factor_evento = 1.4 if dias_evento <= producto.lead_time_dias_china else 1.0
        demanda_diaria_ajustada = demanda_diaria * factor_evento

        periodo_cobertura = producto.lead_time_dias_china + settings.DIAS_SEGURIDAD_STOCK
        punto_reorden = demanda_diaria_ajustada * periodo_cobertura

        en_transito = _pedidos_en_transito(db, producto.id)
        disponible_proyectado = producto.stock_actual + en_transito

        if disponible_proyectado > punto_reorden:
            continue

        cantidad_sugerida = max(0, round(punto_reorden - disponible_proyectado + demanda_diaria_ajustada * 7))

        if producto.stock_actual <= producto.stock_minimo:
            urgencia = "critico"
            mensaje = (
                f"Stock por debajo del mínimo. Con un envío desde China de "
                f"{producto.lead_time_dias_china} días, pide ahora para evitar desabastecimiento."
            )
        else:
            urgencia = "atencion"
            mensaje = "Se acerca al punto de reorden considerando el tiempo de envío desde China."

        if dias_evento <= producto.lead_time_dias_china:
            mensaje += f" Además, faltan {dias_evento} días para {evento_nombre}, temporada de mayor demanda."

        recomendaciones.append(
            schemas.RecommendationOut(
                product_id=producto.id,
                nombre=producto.nombre,
                sku=producto.sku,
                stock_actual=producto.stock_actual,
                punto_reorden=round(punto_reorden, 1),
                demanda_diaria_pronosticada=round(demanda_diaria_ajustada, 2),
                lead_time_dias_china=producto.lead_time_dias_china,
                cantidad_sugerida=int(cantidad_sugerida),
                urgencia=urgencia,
                mensaje=mensaje,
            )
        )

    orden_urgencia = {"critico": 0, "atencion": 1, "ok": 2}
    recomendaciones.sort(key=lambda r: orden_urgencia.get(r.urgencia, 3))
    return recomendaciones
