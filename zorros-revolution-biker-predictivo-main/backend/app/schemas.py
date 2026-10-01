from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ---------- Auth ----------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rol: str
    nombre: str


class UserOut(BaseModel):
    id: int
    nombre: str
    email: EmailStr
    rol: str
    activo: bool

    class Config:
        from_attributes = True


# Política mínima de contraseñas. Se aplica en todos los puntos donde se
# establece una: alta de usuario, restablecimiento por un administrador y cambio
# de la propia. Antes `password: str` aceptaba cualquier cosa, incluso "a".
PASSWORD_MIN_LONGITUD = 10


def validar_password(valor: str) -> str:
    if len(valor) < PASSWORD_MIN_LONGITUD:
        raise ValueError(f"La contraseña debe tener al menos {PASSWORD_MIN_LONGITUD} caracteres")
    if not any(c.isalpha() for c in valor):
        raise ValueError("La contraseña debe incluir al menos una letra")
    if not any(c.isdigit() for c in valor):
        raise ValueError("La contraseña debe incluir al menos un número")
    return valor


ROLES_VALIDOS = ("admin", "cajero")


def validar_rol(valor: str) -> str:
    if valor not in ROLES_VALIDOS:
        raise ValueError(f"Rol inválido. Debe ser uno de: {', '.join(ROLES_VALIDOS)}")
    return valor


class UserCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str
    rol: str = "cajero"

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        return validar_password(v)

    @field_validator("rol")
    @classmethod
    def _rol(cls, v: str) -> str:
        return validar_rol(v)


class UserRolUpdate(BaseModel):
    rol: str

    @field_validator("rol")
    @classmethod
    def _rol(cls, v: str) -> str:
        return validar_rol(v)


class UserEstadoUpdate(BaseModel):
    activo: bool


class PasswordReset(BaseModel):
    """Un administrador establece la contraseña de otro usuario."""

    password_nueva: str

    @field_validator("password_nueva")
    @classmethod
    def _password(cls, v: str) -> str:
        return validar_password(v)


class PasswordChange(BaseModel):
    """Un usuario cambia la suya; debe probar que conoce la actual."""

    password_actual: str
    password_nueva: str

    @field_validator("password_nueva")
    @classmethod
    def _password(cls, v: str) -> str:
        return validar_password(v)


# ---------- Productos ----------
class ProductBase(BaseModel):
    sku: str
    nombre: str
    categoria: str
    precio: float
    costo: float = 0
    stock_minimo: int = 5
    lead_time_dias_china: int = 60


class ProductCreate(ProductBase):
    stock_actual: int = 0


class ProductUpdate(BaseModel):
    nombre: Optional[str] = None
    categoria: Optional[str] = None
    precio: Optional[float] = None
    costo: Optional[float] = None
    stock_minimo: Optional[int] = None
    lead_time_dias_china: Optional[int] = None
    activo: Optional[bool] = None


class ProductOut(ProductBase):
    id: int
    stock_actual: int
    activo: bool

    class Config:
        from_attributes = True


# ---------- Ventas ----------
class SaleItemCreate(BaseModel):
    product_id: int
    cantidad: int = Field(gt=0)


class SaleCreate(BaseModel):
    canal: str = "Tienda"
    metodo_pago: str = "Efectivo"
    items: List[SaleItemCreate]


class SaleItemOut(BaseModel):
    product_id: int
    producto_nombre: str
    cantidad: int
    precio_unitario: float


class SaleOut(BaseModel):
    id: int
    fecha_hora: datetime
    cajero_nombre: str
    canal: str
    total: float
    metodo_pago: str
    items: List[SaleItemOut]


# ---------- Inventario ----------
class StockReceiveRequest(BaseModel):
    product_id: int
    cantidad: int = Field(gt=0)
    nota: Optional[str] = None


class StockAdjustRequest(BaseModel):
    product_id: int
    cantidad: int
    nota: Optional[str] = None


class PurchaseOrderOut(BaseModel):
    id: int
    product_id: int
    producto_nombre: str
    cantidad: int
    fecha_pedido: datetime
    fecha_estimada_llegada: Optional[datetime]
    estado: str
    origen: str


# ---------- Dashboard ----------
class DashboardSummary(BaseModel):
    ventas_dia: float
    ventas_mes: float
    variacion_mes_pct: float
    cantidad_ventas_mes: int
    ticket_promedio: float
    productos_vendidos_mes: int
    stock_critico: int
    proyeccion_proximo_mes: float
    confianza_modelo: Optional[float]


class TrendPoint(BaseModel):
    fecha: str
    real: Optional[float] = None
    proyectado: Optional[float] = None


# ---------- Predicciones ----------
class ForecastPoint(BaseModel):
    fecha: str
    real: Optional[float] = None
    pronostico: Optional[float] = None
    intervalo_inf: Optional[float] = None
    intervalo_sup: Optional[float] = None


class ProductSignal(BaseModel):
    product_id: int
    nombre: str
    categoria: str
    tendencia: str  # "alta_demanda" | "baja_demanda"
    magnitud_pct: float


class RecommendationOut(BaseModel):
    product_id: int
    nombre: str
    sku: str
    stock_actual: int
    punto_reorden: float
    demanda_diaria_pronosticada: float
    lead_time_dias_china: int
    cantidad_sugerida: int
    urgencia: str  # "critico" | "atencion" | "ok"
    mensaje: str


class RetrainResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_run_id: int
    algoritmo: str
    version: str
    mase: Optional[float]
    wape: Optional[float]
    mejora_vs_baseline_pct: Optional[float]
    # Un entrenamiento ya no implica una publicación: el modelo solo reemplaza al
    # anterior si supera la línea base (cap. 2.5.1 de la tesis).
    publicado: bool = False
    motivo: Optional[str] = None
    mejor_candidato: Optional[str] = None


class ModelStatusResponse(BaseModel):
    """Último entrenamiento registrado, se haya publicado o no."""

    model_config = ConfigDict(protected_namespaces=())

    entrenado: bool
    publicado: bool
    model_run_id: Optional[int] = None
    algoritmo: Optional[str] = None
    version: Optional[str] = None
    fecha: Optional[datetime] = None
    mase: Optional[float] = None
    wape: Optional[float] = None
    mejora_vs_baseline_pct: Optional[float] = None
    motivo: Optional[str] = None


# ---------- Perfilamiento de series ----------
class SeriesProfileOut(BaseModel):
    product_id: int
    sku: str
    nombre: str
    categoria: str
    dias_historial: int
    unidades_totales: float
    media_diaria: float
    proporcion_ceros: float
    adi: float  # Average Demand Interval: días por cada día con demanda
    cv2: float  # Coeficiente de variación al cuadrado de las cantidades positivas
    clasificacion: str  # "regular" | "erratica" | "intermitente" | "grumosa"
    estrategia_sugerida: str


class SeriesProfileSummary(BaseModel):
    productos_con_ventas: int
    regular: int
    erratica: int
    intermitente: int
    grumosa: int
    pct_series_intermitentes: float
    pct_volumen_modelable_directo: float


class SeriesProfileResponse(BaseModel):
    resumen: SeriesProfileSummary
    series: List[SeriesProfileOut]
