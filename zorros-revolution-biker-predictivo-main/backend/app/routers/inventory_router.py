from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..deps import get_current_user, get_db, require_role

router = APIRouter(prefix="/inventory", tags=["inventario"])


@router.post("/receive", response_model=schemas.ProductOut)
def receive_stock(
    payload: schemas.StockReceiveRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin", "cajero")),
):
    """Registra stock recibido (p. ej. llegada de un pedido desde China). Disponible para cajero y admin."""
    product = db.query(models.Product).filter(models.Product.id == payload.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    product.stock_actual += payload.cantidad
    db.add(
        models.StockMovement(
            product_id=product.id,
            tipo=models.TipoMovimiento.recepcion,
            cantidad=payload.cantidad,
            usuario_id=current_user.id,
            nota=payload.nota or "Recepción de stock",
        )
    )
    db.commit()
    db.refresh(product)
    return product


@router.post("/adjust", response_model=schemas.ProductOut)
def adjust_stock(
    payload: schemas.StockAdjustRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    product = db.query(models.Product).filter(models.Product.id == payload.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    product.stock_actual = max(0, product.stock_actual + payload.cantidad)
    db.add(
        models.StockMovement(
            product_id=product.id,
            tipo=models.TipoMovimiento.ajuste,
            cantidad=payload.cantidad,
            usuario_id=current_user.id,
            nota=payload.nota or "Ajuste manual",
        )
    )
    db.commit()
    db.refresh(product)
    return product


@router.get("/purchase-orders", response_model=List[schemas.PurchaseOrderOut])
def list_purchase_orders(db: Session = Depends(get_db), _=Depends(get_current_user)):
    orders = db.query(models.PurchaseOrder).order_by(models.PurchaseOrder.fecha_pedido.desc()).all()
    return [
        schemas.PurchaseOrderOut(
            id=o.id,
            product_id=o.product_id,
            producto_nombre=o.product.nombre,
            cantidad=o.cantidad,
            fecha_pedido=o.fecha_pedido,
            fecha_estimada_llegada=o.fecha_estimada_llegada,
            estado=o.estado.value,
            origen=o.origen,
        )
        for o in orders
    ]


@router.post("/purchase-orders", response_model=schemas.PurchaseOrderOut, status_code=201)
def create_purchase_order(
    product_id: int,
    cantidad: int,
    db: Session = Depends(get_db),
    _=Depends(require_role("admin")),
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    eta = datetime.utcnow() + timedelta(days=product.lead_time_dias_china)
    order = models.PurchaseOrder(product_id=product_id, cantidad=cantidad, fecha_estimada_llegada=eta)
    db.add(order)
    db.commit()
    db.refresh(order)
    return schemas.PurchaseOrderOut(
        id=order.id,
        product_id=order.product_id,
        producto_nombre=product.nombre,
        cantidad=order.cantidad,
        fecha_pedido=order.fecha_pedido,
        fecha_estimada_llegada=order.fecha_estimada_llegada,
        estado=order.estado.value,
        origen=order.origen,
    )
