"""Simulador de ventas para poder evaluar el modelo sin datos de la empresa.

No hubo acceso al historico real, asi que las ventas se simulan. Pero un
simulador solo sirve para evaluar si el modelo tiene que DESCUBRIR los
patrones, no si se los regalan. El seed anterior generaba la demanda con las
mismas tres funciones de calendario que el modelo recibe como features
(diciembre, Bono 14, Caravana), de modo que cualquier metrica era circular.

Este modulo no importa el modulo de features de calendario del modelo (hay
una prueba que lo verifica leyendo el codigo fuente). La estacionalidad sale
de mecanismos distintos y mas cercanos a la realidad:

- Fechas concretas del calendario guatemalteco: feriados, quincenas, la semana
  posterior al pago del Bono 14, la del aguinaldo y la Caravana del Zorro como
  un fin de semana concreto (no medio febrero).
- Peso por dia de la semana.
- Demanda diaria Poisson por producto: intermitente por construccion.
- Quiebres de stock: sin existencia la venta se pierde. Es la demanda
  censurada que la tesis describe (cap. 2.1) y que antes nunca se simulo.
- Promociones cortas al azar y una tendencia suave.

Uso:
    python -m app.simular_ventas --meses 12 --confirmar
    docker compose exec api python -m app.simular_ventas --meses 12 --confirmar
"""
from __future__ import annotations

import argparse
import calendar
import random
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models

# ---------------------------------------------------------------------------
# Calendario guatemalteco como fechas concretas
# ---------------------------------------------------------------------------

# La tienda no abre.
FERIADOS_CERRADO = {(1, 1), (12, 25)}

# Abre medio dia o con poca afluencia.
FERIADOS_BAJA = {
    (5, 1),    # Dia del Trabajo
    (6, 30),   # Dia del Ejercito
    (9, 15),   # Independencia
    (10, 20),  # Revolucion
    (11, 1),   # Todos los Santos
    (12, 24),  # Nochebuena, medio dia
    (12, 31),  # Fin de ano, medio dia
}
FACTOR_FERIADO_BAJA = 0.5

# Jueves y Viernes Santo. Semana Santa se mueve cada ano.
SEMANA_SANTA = {
    2024: (date(2024, 3, 28), date(2024, 3, 29)),
    2025: (date(2025, 4, 17), date(2025, 4, 18)),
    2026: (date(2026, 4, 2), date(2026, 4, 3)),
    2027: (date(2027, 3, 25), date(2027, 3, 26)),
}
FACTOR_SEMANA_SANTA = 0.4

# Caravana del Zorro: peregrinacion motociclista a Esquipulas, un sabado
# concreto a fines de enero o inicios de febrero. Los dias previos se compra
# equipo; el sabado la tienda vende poco porque el cliente esta en la ruta.
CARAVANA_DEL_ZORRO: Dict[int, date] = {
    2024: date(2024, 2, 3),
    2025: date(2025, 2, 1),
    2026: date(2026, 1, 31),
    2027: date(2027, 2, 6),
}
FACTOR_PREVIA_CARAVANA = {3: 1.3, 2: 1.6, 1: 1.9}  # dias antes -> factor
FACTOR_DIA_CARAVANA = 0.6

# Quincena: dia 15 y ultimo dia del mes.
FACTOR_QUINCENA = 1.35

# Bono 14 se paga a mas tardar el 15 de julio; el gasto se concentra despues.
BONO14_INICIO, BONO14_FIN = (7, 15), (7, 22)
FACTOR_BONO14 = 1.6

# Aguinaldo se paga a mas tardar el 15 de diciembre; temporada navidena.
AGUINALDO_INICIO, AGUINALDO_FIN = (12, 10), (12, 23)
FACTOR_AGUINALDO = 1.5

# Peso por dia de la semana (lunes = 0). Sabado es el dia fuerte del retail
# de motoaccesorios; domingo abre medio dia.
PESO_DIA_SEMANA = (0.85, 0.80, 0.85, 0.95, 1.10, 1.45, 0.70)


def rango_fechas(hasta: date, meses: int) -> Tuple[date, date]:
    """Ventana de simulacion: `meses` hacia atras desde `hasta`, inclusive."""
    if meses <= 0:
        raise ValueError("meses debe ser un entero positivo")
    ano = hasta.year
    mes = hasta.month - meses
    while mes <= 0:
        mes += 12
        ano -= 1
    dia = min(hasta.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia), hasta


def _es_ultimo_dia_del_mes(fecha: date) -> bool:
    return fecha.day == calendar.monthrange(fecha.year, fecha.month)[1]


def _entre(fecha: date, inicio: Tuple[int, int], fin: Tuple[int, int]) -> bool:
    return inicio <= (fecha.month, fecha.day) <= fin


def factor_calendario(fecha: date) -> float:
    """Multiplicador de demanda por fecha concreta. 1.0 = dia normal, 0 = cerrado."""
    clave = (fecha.month, fecha.day)
    if clave in FERIADOS_CERRADO:
        return 0.0

    factor = 1.0
    if clave in FERIADOS_BAJA:
        factor *= FACTOR_FERIADO_BAJA
    if fecha in SEMANA_SANTA.get(fecha.year, ()):
        factor *= FACTOR_SEMANA_SANTA
    if fecha.day == 15 or _es_ultimo_dia_del_mes(fecha):
        factor *= FACTOR_QUINCENA
    if _entre(fecha, BONO14_INICIO, BONO14_FIN):
        factor *= FACTOR_BONO14
    if _entre(fecha, AGUINALDO_INICIO, AGUINALDO_FIN):
        factor *= FACTOR_AGUINALDO

    caravana = CARAVANA_DEL_ZORRO.get(fecha.year)
    if caravana is not None:
        dias_antes = (caravana - fecha).days
        if dias_antes == 0:
            factor *= FACTOR_DIA_CARAVANA
        elif dias_antes in FACTOR_PREVIA_CARAVANA:
            factor *= FACTOR_PREVIA_CARAVANA[dias_antes]

    return factor


def peso_dia_semana(fecha: date) -> float:
    return PESO_DIA_SEMANA[fecha.weekday()]


# ---------------------------------------------------------------------------
# Simulacion contra la base de datos
# ---------------------------------------------------------------------------

# Unidades/dia por producto en un dia normal. El rango produce ~0.3 en
# promedio, que es lo que arrojo el perfilamiento del catalogo.
TASA_BASE_MIN, TASA_BASE_MAX = 0.12, 0.60

# Reabastecimiento: cada cuantos dias llega pedido y para cuantos dias se
# compra. Comprar justo lo del periodo hace que los picos estacionales agoten
# el stock: asi aparecen los quiebres (demanda censurada).
DIAS_ENTRE_PEDIDOS_MIN, DIAS_ENTRE_PEDIDOS_MAX = 50, 75
DIAS_DE_COBERTURA_POR_PEDIDO = 60
STOCK_INICIAL_DIAS = 45

# Promociones: probabilidad diaria de que arranque una para un producto, su
# duracion y su efecto sobre la demanda.
PROB_INICIO_PROMO = 0.012
DURACION_PROMO_MIN, DURACION_PROMO_MAX = 3, 7
FACTOR_PROMO = 1.8

# Crecimiento suave a lo largo de la ventana.
TENDENCIA_INICIO, TENDENCIA_FIN = 0.9, 1.1

HORA_APERTURA, HORA_CIERRE = 9, 19
PROB_VENTA_POR_CAJERO = 0.8
CANALES = ("Tienda", "Tienda", "Tienda", "En línea")
METODOS_PAGO = ("Efectivo", "Tarjeta", "Transferencia", "Crédito")
ITEMS_POR_TICKET = (1, 1, 1, 2, 2, 3)


@dataclass
class Configuracion:
    meses: int = 12
    hasta: date = field(default_factory=date.today)
    semilla: int = 42


@dataclass
class Resumen:
    inicio: date
    fin: date
    ventas: int
    unidades: int
    ventas_perdidas_por_stock: int
    dias_con_ventas: int


@dataclass
class _EstadoProducto:
    producto: models.Product
    tasa_base: float
    stock: int = 0
    proximo_pedido: date = date.min
    promo_hasta: date = date.min


def _hay_ventas(db: Session) -> bool:
    return db.query(func.count(models.Sale.id)).scalar() > 0


def _limpiar(db: Session) -> None:
    """Borra ventas y movimientos. Usuarios y productos se conservan."""
    db.query(models.SaleItem).delete()
    db.query(models.Sale).delete()
    db.query(models.StockMovement).delete()
    db.query(models.PurchaseOrder).delete()
    for p in db.query(models.Product):
        p.stock_actual = 0
    db.commit()


def _recibir_stock(db: Session, estado: _EstadoProducto, cantidad: int, fecha: date,
                   usuario_id: int, nota: str) -> None:
    estado.stock += cantidad
    db.add(models.StockMovement(
        product_id=estado.producto.id, tipo=models.TipoMovimiento.recepcion, cantidad=cantidad,
        usuario_id=usuario_id, fecha=datetime(fecha.year, fecha.month, fecha.day, 8, 30), nota=nota,
    ))


def _tendencia(fecha: date, inicio: date, fin: date) -> float:
    avance = (fecha - inicio).days / max(1, (fin - inicio).days)
    return TENDENCIA_INICIO + (TENDENCIA_FIN - TENDENCIA_INICIO) * avance


def _demanda_del_dia(rng_np, estado: _EstadoProducto, fecha: date, factor_dia: float) -> int:
    factor_promo = FACTOR_PROMO if fecha <= estado.promo_hasta else 1.0
    return int(rng_np.poisson(estado.tasa_base * factor_dia * factor_promo))


def _agrupar_en_tickets(rng: random.Random, unidades: List[int]) -> List[dict]:
    """Convierte una lista de product_id (una entrada por unidad) en tickets."""
    rng.shuffle(unidades)
    tickets = []
    while unidades:
        n = min(rng.choice(ITEMS_POR_TICKET), len(unidades))
        lineas: dict = {}
        for pid in unidades[:n]:
            lineas[pid] = lineas.get(pid, 0) + 1
        tickets.append(lineas)
        unidades = unidades[n:]
    return tickets


def _registrar_ticket(db: Session, rng: random.Random, lineas: dict, estados: dict,
                      fecha: date, cajero_id: int, admin_id: int) -> int:
    hora = rng.randint(HORA_APERTURA, HORA_CIERRE)
    fecha_hora = datetime(fecha.year, fecha.month, fecha.day, hora, rng.randint(0, 59))
    vendedor = cajero_id if rng.random() < PROB_VENTA_POR_CAJERO else admin_id

    venta = models.Sale(fecha_hora=fecha_hora, cajero_id=vendedor, canal=rng.choice(CANALES),
                        metodo_pago=rng.choice(METODOS_PAGO), total=0.0)
    db.add(venta)
    db.flush()

    total = 0.0
    unidades = 0
    for pid, cantidad in lineas.items():
        precio = estados[pid].producto.precio
        db.add(models.SaleItem(sale_id=venta.id, product_id=pid, cantidad=cantidad, precio_unitario=precio))
        db.add(models.StockMovement(product_id=pid, tipo=models.TipoMovimiento.venta, cantidad=cantidad,
                                    usuario_id=vendedor, fecha=fecha_hora, nota=f"Venta #{venta.id}"))
        total += cantidad * precio
        unidades += cantidad
    venta.total = round(total, 2)
    return unidades


def _inicializar_estados(rng: random.Random, productos, inicio: date) -> dict:
    estados = {}
    for p in productos:
        dias = rng.randint(DIAS_ENTRE_PEDIDOS_MIN, DIAS_ENTRE_PEDIDOS_MAX)
        estados[p.id] = _EstadoProducto(
            producto=p,
            tasa_base=rng.uniform(TASA_BASE_MIN, TASA_BASE_MAX),
            proximo_pedido=inicio + timedelta(days=dias),
        )
    return estados


def _actualizar_pedidos_y_promos(db, rng, estados, fecha, admin_id) -> None:
    for estado in estados.values():
        if fecha >= estado.proximo_pedido:
            lote = max(1, int(estado.tasa_base * DIAS_DE_COBERTURA_POR_PEDIDO))
            _recibir_stock(db, estado, lote, fecha, admin_id, "Pedido China")
            dias = rng.randint(DIAS_ENTRE_PEDIDOS_MIN, DIAS_ENTRE_PEDIDOS_MAX)
            estado.proximo_pedido = fecha + timedelta(days=dias)
        if fecha > estado.promo_hasta and rng.random() < PROB_INICIO_PROMO:
            estado.promo_hasta = fecha + timedelta(days=rng.randint(DURACION_PROMO_MIN, DURACION_PROMO_MAX))


def _simular_dia(db, rng, rng_np, estados, fecha, inicio, fin, admin_id, cajero_id) -> Tuple[int, int, int]:
    """Devuelve (tickets, unidades, unidades perdidas por falta de stock) del dia."""
    _actualizar_pedidos_y_promos(db, rng, estados, fecha, admin_id)

    factor_dia = factor_calendario(fecha) * peso_dia_semana(fecha) * _tendencia(fecha, inicio, fin)
    if factor_dia == 0:
        return 0, 0, 0

    pool: List[int] = []
    perdidas = 0
    for pid, estado in estados.items():
        demanda = _demanda_del_dia(rng_np, estado, fecha, factor_dia)
        vendido = min(demanda, estado.stock)
        perdidas += demanda - vendido
        estado.stock -= vendido
        pool.extend([pid] * vendido)

    tickets = _agrupar_en_tickets(rng, pool)
    unidades = sum(_registrar_ticket(db, rng, lineas, estados, fecha, cajero_id, admin_id) for lineas in tickets)
    return len(tickets), unidades, perdidas


def simular(db: Session, config: Configuracion, confirmar: bool = False) -> Resumen:
    """Reemplaza el historico de ventas por una simulacion de `config.meses` meses."""
    if _hay_ventas(db):
        if not confirmar:
            raise ValueError(
                "Ya existen ventas registradas. Vuelve a ejecutar con --confirmar para "
                "borrarlas y reemplazarlas por la simulacion."
            )
        _limpiar(db)

    admin = db.query(models.User).filter(models.User.rol == models.RolUsuario.admin).first()
    cajero = db.query(models.User).filter(models.User.rol == models.RolUsuario.cajero).first() or admin
    productos = db.query(models.Product).filter(models.Product.activo.is_(True)).all()
    if admin is None or not productos:
        raise ValueError("Hacen falta al menos un administrador y un producto activo.")

    inicio, fin = rango_fechas(config.hasta, config.meses)
    rng = random.Random(config.semilla)
    rng_np = np.random.default_rng(config.semilla)
    estados = _inicializar_estados(rng, productos, inicio)

    for estado in estados.values():
        lote = max(1, int(estado.tasa_base * STOCK_INICIAL_DIAS))
        _recibir_stock(db, estado, lote, inicio, admin.id, "Inventario inicial")

    ventas = unidades = perdidas = dias_con_ventas = 0
    fecha = inicio
    while fecha <= fin:
        v, u, p = _simular_dia(db, rng, rng_np, estados, fecha, inicio, fin, admin.id, cajero.id)
        ventas, unidades, perdidas = ventas + v, unidades + u, perdidas + p
        dias_con_ventas += 1 if v else 0
        fecha += timedelta(days=1)

    for estado in estados.values():
        estado.producto.stock_actual = estado.stock
    db.commit()

    return Resumen(inicio=inicio, fin=fin, ventas=ventas, unidades=unidades,
                   ventas_perdidas_por_stock=perdidas, dias_con_ventas=dias_con_ventas)


# ---------------------------------------------------------------------------
# Linea de comandos
# ---------------------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m app.simular_ventas",
        description="Reemplaza el historico de ventas por una simulacion realista.",
    )
    p.add_argument("--meses", type=int, default=12, help="meses de historial a generar (default 12)")
    p.add_argument("--hasta", type=date.fromisoformat, default=None,
                   help="ultimo dia de la simulacion, AAAA-MM-DD (default hoy)")
    p.add_argument("--semilla", type=int, default=42, help="semilla para reproducibilidad")
    p.add_argument("--confirmar", action="store_true",
                   help="obligatorio si ya hay ventas: se BORRAN y se reemplazan")
    return p


def _imprimir(resumen: Resumen) -> None:
    dias = (resumen.fin - resumen.inicio).days + 1
    print(f"\nSimulacion completada: {resumen.inicio} -> {resumen.fin} ({dias} dias)")
    print(f"  ventas (tickets):            {resumen.ventas:>7}")
    print(f"  unidades vendidas:           {resumen.unidades:>7}")
    print(f"  dias con al menos una venta: {resumen.dias_con_ventas:>7} de {dias}")
    print(f"  unidades perdidas por falta de stock: {resumen.ventas_perdidas_por_stock}")
    print("\nSiguiente paso: Predicciones -> Recalibrar Modelo (solo admin).")


def ejecutar(argv: Optional[List[str]] = None, db: Optional[Session] = None) -> Resumen:
    """Punto de entrada testeable: recibe argumentos y sesion explicitos."""
    args = _parser().parse_args(argv)
    config = Configuracion(meses=args.meses, hasta=args.hasta or date.today(), semilla=args.semilla)

    propia = db is None
    if propia:
        from .database import SessionLocal
        db = SessionLocal()
    try:
        resumen = simular(db, config, confirmar=args.confirmar)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    finally:
        if propia:
            db.close()

    _imprimir(resumen)
    return resumen


def main() -> None:
    ejecutar()


if __name__ == "__main__":
    main()
