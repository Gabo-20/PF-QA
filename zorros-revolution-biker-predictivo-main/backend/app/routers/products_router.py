from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..deps import get_current_user, get_db, require_role

router = APIRouter(prefix="/products", tags=["productos"])


@router.get("", response_model=List[schemas.ProductOut])
def list_products(solo_activos: bool = True, db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(models.Product)
    if solo_activos:
        q = q.filter(models.Product.activo == True)  # noqa: E712
    return q.order_by(models.Product.nombre).all()


@router.get("/stock-bajo", response_model=List[schemas.ProductOut])
def stock_bajo(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return (
        db.query(models.Product)
        .filter(models.Product.activo == True, models.Product.stock_actual <= models.Product.stock_minimo)  # noqa: E712
        .order_by(models.Product.stock_actual)
        .all()
    )


@router.post("", response_model=schemas.ProductOut, status_code=201)
def create_product(payload: schemas.ProductCreate, db: Session = Depends(get_db), _=Depends(require_role("admin"))):
    if db.query(models.Product).filter(models.Product.sku == payload.sku).first():
        raise HTTPException(status_code=400, detail="El SKU ya existe")
    product = models.Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.put("/{product_id}", response_model=schemas.ProductOut)
def update_product(
    product_id: int,
    payload: schemas.ProductUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_role("admin")),
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db), _=Depends(require_role("admin"))):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    product.activo = False
    db.commit()
    return None
