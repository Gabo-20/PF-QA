"""Genera datos de demostración: usuarios, catálogo de motoaccesorios y 12 meses
de ventas simuladas, para que el dashboard y las predicciones muestren resultados
desde el primer arranque.

Las ventas las genera `simular_ventas`, que no comparte ninguna función con las
features del modelo (el generador anterior sí lo hacía, y eso volvía circular
cualquier métrica). Para regenerar solo las ventas sobre una base ya sembrada:

    python -m app.simular_ventas --meses 12 --confirmar

Uso:
    python -m app.seed_data
"""
import secrets
import string

from sqlalchemy.orm import Session

from . import models
from .database import Base, SessionLocal, engine
from .security import hash_password
from .simular_ventas import Configuracion, simular

# sku, nombre, categoria, precio, costo, stock_actual, lead_time_dias_china
CATALOGO = [
    ("CAS-XR700", "Casco Integral XR-700 Matte Black", "Protección", 850.0, 520.0, 45, 60),
    ("CAS-AGV-PISTA", "Casco AGV Pista", "Protección", 3200.0, 2100.0, 25, 75),
    ("CAS-ABIERTO-01", "Casco Abierto Urbano", "Protección", 420.0, 260.0, 60, 55),
    ("CHQ-VMAX-PRO", "Chaqueta Armadura V-Max Pro", "Indumentaria", 980.0, 610.0, 40, 65),
    ("CHQ-CUERO-CL", "Chaqueta de Cuero Clásica", "Indumentaria", 1150.0, 700.0, 30, 70),
    ("CHQ-LLUVIA", "Chaqueta Impermeable de Lluvia", "Indumentaria", 350.0, 190.0, 55, 50),
    ("GTE-ALPINE", "Guantes Alpinestars", "Indumentaria", 320.0, 180.0, 70, 45),
    ("GTE-INVIERNO", "Guantes de Invierno Térmicos", "Indumentaria", 280.0, 150.0, 50, 45),
    ("FRE-BREMBO", "Pastillas de Freno Brembo", "Consumibles", 380.0, 210.0, 90, 40),
    ("FRE-ORG", "Pastillas de Freno Orgánicas", "Consumibles", 190.0, 95.0, 100, 40),
    ("LLA-LLUVIA", "Llanta para Lluvia 120/70", "Consumibles", 750.0, 460.0, 35, 55),
    ("LLA-DEPORTIVA", "Llanta Deportiva 180/55", "Consumibles", 1450.0, 950.0, 20, 60),
    ("ACC-CANDADO", "Candado de Disco Antirrobo", "Accesorios", 210.0, 110.0, 80, 35),
    ("ACC-MALETA", "Maleta Lateral Rígida", "Accesorios", 1650.0, 1050.0, 15, 70),
    ("ACC-PARABRISAS", "Parabrisas Deportivo Ahumado", "Accesorios", 480.0, 290.0, 25, 60),
    ("ACC-ESPEJOS", "Espejos Retrovisores CNC", "Accesorios", 260.0, 140.0, 60, 40),
    ("ACC-LUCES-LED", "Kit de Luces LED", "Accesorios", 390.0, 210.0, 50, 45),
    ("ACC-COVER", "Funda Cobertora para Moto", "Accesorios", 220.0, 120.0, 65, 35),
    ("BOT-RACING", "Botas Racing Reforzadas", "Indumentaria", 890.0, 540.0, 30, 65),
    ("BOT-URBANA", "Botas Urbanas Casual Biker", "Indumentaria", 540.0, 320.0, 40, 55),
    ("ACC-BAUL", "Baúl Trasero 45L", "Accesorios", 720.0, 430.0, 20, 65),
    ("ACC-PORTA", "Portaequipaje Trasero", "Accesorios", 310.0, 170.0, 35, 40),
    ("CAS-VISOR", "Visera de Repuesto para Casco", "Protección", 150.0, 70.0, 90, 30),
    ("GTE-VERANO", "Guantes de Verano Ventilados", "Indumentaria", 190.0, 95.0, 60, 40),
    ("FRE-DISCO", "Disco de Freno Flotante", "Consumibles", 620.0, 380.0, 25, 55),
]

USUARIOS_DEMO = [
    {"nombre": "Administrador Principal", "email": "admin@zorrosrevolution.com", "rol": "admin"},
    {"nombre": "Cajero de Turno", "email": "cajero@zorrosrevolution.com", "rol": "cajero"},
]

# Meses de historial simulado. Con 12 el modelo ve cada evento anual una vez;
# con menos, diciembre o la Caravana pueden quedar fuera de la ventana.
MESES_HISTORIAL = 12


def _password_aleatoria(longitud: int = 16) -> str:
    """Contraseña fuerte que cumple la política, generada al azar.

    Antes las contraseñas estaban escritas en este archivo y publicadas en el
    README, de modo que cualquiera que viera el repositorio podía entrar a una
    instancia desplegada. Ahora se generan una sola vez, se imprimen y solo
    queda su hash en la base: no viven ni en el código ni en el .env.
    """
    alfabeto = string.ascii_letters + string.digits
    while True:
        clave = "".join(secrets.choice(alfabeto) for _ in range(longitud))
        if any(c.isalpha() for c in clave) and any(c.isdigit() for c in clave):
            return clave


def _crear_usuarios(db: Session) -> dict:
    """Crea los usuarios que falten y devuelve las contraseñas generadas."""
    generadas = {}
    for u in USUARIOS_DEMO:
        if db.query(models.User).filter(models.User.email == u["email"]).first():
            continue
        clave = _password_aleatoria()
        generadas[u["email"]] = clave
        db.add(
            models.User(
                nombre=u["nombre"],
                email=u["email"],
                password_hash=hash_password(clave),
                rol=models.RolUsuario(u["rol"]),
            )
        )
    db.commit()
    return generadas


def _crear_catalogo(db: Session):
    productos = []
    for sku, nombre, categoria, precio, costo, stock, lead_time in CATALOGO:
        producto = db.query(models.Product).filter(models.Product.sku == sku).first()
        if not producto:
            producto = models.Product(
                sku=sku,
                nombre=nombre,
                categoria=categoria,
                precio=precio,
                costo=costo,
                stock_actual=stock,
                stock_minimo=max(8, int(stock * 0.15)),
                lead_time_dias_china=lead_time,
            )
            db.add(producto)
        productos.append(producto)
    db.commit()
    for p in productos:
        db.refresh(p)
    return productos


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        generadas = _crear_usuarios(db)
        _crear_catalogo(db)
        # El simulador busca por si mismo al admin y al cajero, y deja el
        # stock_actual de cada producto coherente con lo que simulo.
        if not db.query(models.Sale).first():
            simular(db, Configuracion(meses=MESES_HISTORIAL))

        print("\nDatos de demostración creados correctamente.")
        if generadas:
            print("\n" + "=" * 68)
            print("CONTRASEÑAS GENERADAS — SE MUESTRAN UNA SOLA VEZ")
            print("=" * 68)
            for email, clave in generadas.items():
                print(f"  {email}\n    {clave}")
            print("=" * 68)
            print("Anótalas ahora: solo queda su hash en la base de datos.")
            print("Cámbialas desde Administración → Usuarios al primer ingreso.")
            print("=" * 68)
        else:
            print("Los usuarios ya existían: sus contraseñas no se modificaron.")
            print("Si perdiste el acceso, usa:  python -m app.manage_users")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
