from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..deps import get_current_user, get_db
from ..ml import forecasting

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=schemas.DashboardSummary)
def summary(db: Session = Depends(get_db), _=Depends(get_current_user)):
    now = datetime.utcnow()
    inicio_mes = datetime(now.year, now.month, 1)
    inicio_hoy = datetime(now.year, now.month, now.day)
    mes_anterior_fin = inicio_mes - timedelta(seconds=1)
    mes_anterior_inicio = datetime(mes_anterior_fin.year, mes_anterior_fin.month, 1)

    ventas_dia = db.query(func.coalesce(func.sum(models.Sale.total), 0.0)).filter(
        models.Sale.fecha_hora >= inicio_hoy
    ).scalar()
    ventas_mes = db.query(func.coalesce(func.sum(models.Sale.total), 0.0)).filter(
        models.Sale.fecha_hora >= inicio_mes
    ).scalar()
    ventas_mes_anterior = db.query(func.coalesce(func.sum(models.Sale.total), 0.0)).filter(
        models.Sale.fecha_hora >= mes_anterior_inicio, models.Sale.fecha_hora < inicio_mes
    ).scalar()

    cantidad_ventas_mes = db.query(func.count(models.Sale.id)).filter(models.Sale.fecha_hora >= inicio_mes).scalar() or 0
    ticket_promedio = (ventas_mes / cantidad_ventas_mes) if cantidad_ventas_mes else 0.0

    productos_vendidos_mes = (
        db.query(func.coalesce(func.sum(models.SaleItem.cantidad), 0))
        .join(models.Sale)
        .filter(models.Sale.fecha_hora >= inicio_mes)
        .scalar()
    ) or 0

    stock_critico = db.query(func.count(models.Product.id)).filter(
        models.Product.activo == True,  # noqa: E712
        models.Product.stock_actual <= models.Product.stock_minimo,
    ).scalar() or 0

    variacion_mes_pct = 0.0
    if ventas_mes_anterior:
        variacion_mes_pct = ((ventas_mes - ventas_mes_anterior) / ventas_mes_anterior) * 100

    proyeccion, confianza = forecasting.proyeccion_proximo_mes(db)

    return schemas.DashboardSummary(
        ventas_dia=round(ventas_dia, 2),
        ventas_mes=round(ventas_mes, 2),
        variacion_mes_pct=round(variacion_mes_pct, 1),
        cantidad_ventas_mes=cantidad_ventas_mes,
        ticket_promedio=round(ticket_promedio, 2),
        productos_vendidos_mes=productos_vendidos_mes,
        stock_critico=stock_critico,
        proyeccion_proximo_mes=proyeccion,
        confianza_modelo=confianza,
    )


@router.get("/trend", response_model=List[schemas.TrendPoint])
def trend(meses: int = 12, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return forecasting.tendencia_mensual(db, meses)
