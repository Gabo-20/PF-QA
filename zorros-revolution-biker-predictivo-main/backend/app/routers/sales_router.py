from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..deps import get_current_user, get_db, require_role

router = APIRouter(prefix="/sales", tags=["ventas"])


def _serialize_sale(sale: models.Sale) -> schemas.SaleOut:
    return schemas.SaleOut(
        id=sale.id,
        fecha_hora=sale.fecha_hora,
        cajero_nombre=sale.cajero.nombre,
        canal=sale.canal,
        total=sale.total,
        metodo_pago=sale.metodo_pago,
        items=[
            schemas.SaleItemOut(
                product_id=i.product_id,
                producto_nombre=i.product.nombre,
                cantidad=i.cantidad,
                precio_unitario=i.precio_unitario,
            )
            for i in sale.items
        ],
    )


@router.get("", response_model=List[schemas.SaleOut])
def list_sales(limit: int = 50, offset: int = 0, db: Session = Depends(get_db), _=Depends(get_current_user)):
    sales = (
        db.query(models.Sale)
        .options(joinedload(models.Sale.items).joinedload(models.SaleItem.product), joinedload(models.Sale.cajero))
        .order_by(models.Sale.fecha_hora.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_serialize_sale(s) for s in sales]


@router.post("", response_model=schemas.SaleOut, status_code=201)
def create_sale(
    payload: schemas.SaleCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin", "cajero")),
):
    if not payload.items:
        raise HTTPException(status_code=400, detail="La venta debe tener al menos un producto")

    sale = models.Sale(cajero_id=current_user.id, canal=payload.canal, metodo_pago=payload.metodo_pago, total=0)
    db.add(sale)
    db.flush()

    total = 0.0
    for item in payload.items:
        product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
        if not product or not product.activo:
            raise HTTPException(status_code=404, detail=f"Producto {item.product_id} no encontrado")
        if product.stock_actual < item.cantidad:
            raise HTTPException(status_code=400, detail=f"Stock insuficiente para {product.nombre}")

        product.stock_actual -= item.cantidad
        subtotal = product.precio * item.cantidad
        total += subtotal

        db.add(
            models.SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                cantidad=item.cantidad,
                precio_unitario=product.precio,
            )
        )
        db.add(
            models.StockMovement(
                product_id=product.id,
                tipo=models.TipoMovimiento.venta,
                cantidad=-item.cantidad,
                usuario_id=current_user.id,
                nota=f"Venta #{sale.id}",
            )
        )

    sale.total = round(total, 2)
    db.commit()
    db.refresh(sale)
    return _serialize_sale(sale)
