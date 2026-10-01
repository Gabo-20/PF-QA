import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base


class RolUsuario(str, enum.Enum):
    admin = "admin"
    cajero = "cajero"


class EstadoPedido(str, enum.Enum):
    pendiente = "pendiente"
    en_transito = "en_transito"
    recibido = "recibido"


class TipoMovimiento(str, enum.Enum):
    venta = "venta"
    recepcion = "recepcion"
    ajuste = "ajuste"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(120), nullable=False)
    email = Column(String(180), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    rol = Column(Enum(RolUsuario), nullable=False, default=RolUsuario.cajero)
    activo = Column(Boolean, default=True, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow)

    ventas = relationship("Sale", back_populates="cajero")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    sku = Column(String(50), unique=True, nullable=False, index=True)
    nombre = Column(String(150), nullable=False)
    categoria = Column(String(80), nullable=False)
    precio = Column(Float, nullable=False)
    costo = Column(Float, nullable=False, default=0)
    stock_actual = Column(Integer, nullable=False, default=0)
    stock_minimo = Column(Integer, nullable=False, default=5)
    # Tiempo de envío estimado desde el proveedor en China, en días.
    lead_time_dias_china = Column(Integer, nullable=False, default=60)
    activo = Column(Boolean, default=True, nullable=False)

    items_venta = relationship("SaleItem", back_populates="product")
    movimientos = relationship("StockMovement", back_populates="product")
    pedidos = relationship("PurchaseOrder", back_populates="product")


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True)
    fecha_hora = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    cajero_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    canal = Column(String(40), default="Tienda")
    total = Column(Float, nullable=False, default=0)
    metodo_pago = Column(String(40), default="Efectivo")

    cajero = relationship("User", back_populates="ventas")
    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")


class SaleItem(Base):
    __tablename__ = "sale_items"

    id = Column(Integer, primary_key=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    precio_unitario = Column(Float, nullable=False)

    sale = relationship("Sale", back_populates="items")
    product = relationship("Product", back_populates="items_venta")


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    tipo = Column(Enum(TipoMovimiento), nullable=False)
    cantidad = Column(Integer, nullable=False)
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow)
    nota = Column(String(255), nullable=True)

    product = relationship("Product", back_populates="movimientos")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    fecha_pedido = Column(DateTime, default=datetime.utcnow)
    fecha_estimada_llegada = Column(DateTime, nullable=True)
    estado = Column(Enum(EstadoPedido), default=EstadoPedido.pendiente)
    origen = Column(String(40), default="China")

    product = relationship("Product", back_populates="pedidos")


class ModelRun(Base):
    __tablename__ = "model_runs"

    id = Column(Integer, primary_key=True)
    algoritmo = Column(String(80), nullable=False)
    version = Column(String(40), nullable=False)
    mase = Column(Float, nullable=True)
    wape = Column(Float, nullable=True)
    fecha = Column(DateTime, default=datetime.utcnow)
    parametros_json = Column(Text, nullable=True)

    forecasts = relationship("Forecast", back_populates="model_run")


class Forecast(Base):
    __tablename__ = "forecasts"

    id = Column(Integer, primary_key=True)
    model_run_id = Column(Integer, ForeignKey("model_runs.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    fecha_objetivo = Column(DateTime, nullable=False, index=True)
    valor = Column(Float, nullable=False)
    intervalo_inf = Column(Float, nullable=True)
    intervalo_sup = Column(Float, nullable=True)

    model_run = relationship("ModelRun", back_populates="forecasts")
    product = relationship("Product")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    accion = Column(String(80), nullable=False)
    entidad = Column(String(80), nullable=False)
    entidad_id = Column(Integer, nullable=True)
    fecha = Column(DateTime, default=datetime.utcnow)
    detalle = Column(Text, nullable=True)
