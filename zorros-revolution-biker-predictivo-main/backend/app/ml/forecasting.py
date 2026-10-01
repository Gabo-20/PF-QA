"""Motor de pronóstico de ventas: entrena el modelo y sirve predicciones al dashboard.

Enfoque:
  - Baseline obligatorio: naive estacional (mismo día de la semana, 7 días atrás).
  - Modelo principal: GradientBoostingRegressor (scikit-learn) sobre features de
    calendario (incluida la estacionalidad de Guatemala) + rezagos + medias móviles.
  - El modelo se persiste con joblib y cada entrenamiento queda registrado en
    la tabla model_runs con sus métricas (MASE / WAPE) para trazabilidad.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from . import baselines, evaluation, metrics
from . import calendar_features as cf

ARTIFACTS_DIR = settings.ARTIFACTS_DIR or os.path.join(os.path.dirname(__file__), "artifacts")
MODEL_PATH = os.path.join(ARTIFACTS_DIR, "sales_model.joblib")
MIN_DIAS_ENTRENAMIENTO = 60

# Un solo lugar para los hiperparámetros: antes estaban repetidos en tres sitios
# (el modelo de evaluación, el final y el JSON de trazabilidad), de modo que
# cambiar uno sin los otros dejaba un registro que mentía sobre lo entrenado.
HIPERPARAMETROS = {"random_state": 42, "n_estimators": 200, "max_depth": 3, "learning_rate": 0.05}

# Horizonte con el que se compara a los candidatos. Se usa 30 días porque es el
# que consume el dashboard: evaluar a 7 y publicar para 30 sería medir otra cosa.
HORIZONTE_EVALUACION = 30
N_VENTANAS_EVALUACION = 5

os.makedirs(ARTIFACTS_DIR, exist_ok=True)

FEATURE_COLUMNS = [
    "dia_semana", "es_fin_de_semana", "mes", "mes_sin", "mes_cos", "dia_mes",
    "is_diciembre", "is_semana_bono14", "is_caravana_zorro",
    "lag_1", "lag_7", "lag_14", "lag_30", "media_movil_7", "media_movil_30",
]


def _ventas_diarias(db: Session) -> pd.DataFrame:
    """Serie de ventas totales por día (rellenando días sin ventas con 0)."""
    filas = (
        db.query(
            func.date(models.Sale.fecha_hora).label("fecha"),
            func.sum(models.Sale.total).label("total"),
        )
        .group_by(func.date(models.Sale.fecha_hora))
        .order_by(func.date(models.Sale.fecha_hora))
        .all()
    )
    if not filas:
        return pd.DataFrame(columns=["fecha", "total"])

    df = pd.DataFrame(filas, columns=["fecha", "total"])
    df["fecha"] = pd.to_datetime(df["fecha"])
    df = df.set_index("fecha").asfreq("D", fill_value=0.0).reset_index()
    df["total"] = df["total"].astype(float)
    return df


def _construir_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    cal = df["fecha"].apply(lambda d: pd.Series(cf.features_dict(d)))
    df = pd.concat([df, cal], axis=1)

    for lag in (1, 7, 14, 30):
        df[f"lag_{lag}"] = df["total"].shift(lag)
    df["media_movil_7"] = df["total"].shift(1).rolling(7).mean()
    df["media_movil_30"] = df["total"].shift(1).rolling(30).mean()
    return df


def _wape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    denom = np.sum(np.abs(y_true))
    if denom == 0:
        return 0.0
    return float(np.sum(np.abs(y_true - y_pred)) / denom * 100)


def _mase(y_true: np.ndarray, y_pred: np.ndarray, y_naive: np.ndarray) -> float:
    mae_modelo = float(np.mean(np.abs(y_true - y_pred)))
    mae_naive = float(np.mean(np.abs(y_true - y_naive)))
    if mae_naive == 0:
        return 0.0
    return mae_modelo / mae_naive


def _pronosticador_gbr(df: pd.DataFrame):
    """Devuelve un pronosticador con la misma interfaz que las líneas base.

    Reentrena el GradientBoosting en cada llamada usando SOLO el prefijo de la
    serie que recibe, que es lo que hace honesta la validación de origen móvil:
    en cada ventana el modelo se entrena como si estuviera parado en esa fecha.
    """

    def pronosticar(y_entrenamiento, h):
        sub = df.iloc[: len(y_entrenamiento)]
        feats = _construir_features(sub).dropna().reset_index(drop=True)
        if len(feats) < 30:
            raise ValueError("historial insuficiente tras calcular rezagos")
        modelo = GradientBoostingRegressor(**HIPERPARAMETROS)
        modelo.fit(feats[FEATURE_COLUMNS], feats["total"])
        return np.array([valor for _, valor in _predecir_recursivo(modelo, sub, h)], dtype=float)

    return pronosticar


def _guardar_artefacto(modelo, version: str) -> str:
    """Escribe el modelo de forma atómica y conserva una copia versionada.

    Antes se hacía `joblib.dump` directamente sobre la ruta activa: un
    entrenamiento concurrente con una petición de pronóstico podía cargar un
    pickle a medio escribir. `os.replace` es atómico dentro del mismo sistema
    de archivos. La copia versionada permite auditar y revertir (RF-09).
    """
    ruta_versionada = os.path.join(ARTIFACTS_DIR, f"sales_model_{version}.joblib")
    joblib.dump(modelo, ruta_versionada)

    temporal = MODEL_PATH + ".tmp"
    joblib.dump(modelo, temporal)
    os.replace(temporal, MODEL_PATH)
    return ruta_versionada


def entrenar_modelo(db: Session) -> schemas.RetrainResponse:
    """Compara el modelo de IA contra las líneas base y publica solo si gana.

    Implementa el cap. 2.5 de la tesis: validación temporal con origen móvil,
    métricas escaladas y criterio de aceptación. Si ningún candidato supera la
    referencia, NO se publica nada y el modelo anterior se conserva intacto.
    """
    df = _ventas_diarias(db)
    if len(df) < MIN_DIAS_ENTRENAMIENTO:
        raise ValueError(
            f"Se necesitan al menos {MIN_DIAS_ENTRENAMIENTO} días de historial de ventas para entrenar el modelo."
        )

    feats = _construir_features(df).dropna().reset_index(drop=True)
    if len(feats) < 30:
        raise ValueError("No hay suficientes datos históricos (tras calcular rezagos) para entrenar el modelo.")

    serie = df["total"].to_numpy(dtype=float)
    h = HORIZONTE_EVALUACION

    if evaluation.ventanas_disponibles(serie.size, h, MIN_DIAS_ENTRENAMIENTO, N_VENTANAS_EVALUACION) == 0:
        raise ValueError(
            f"Se necesitan al menos {MIN_DIAS_ENTRENAMIENTO + h} días de historial para evaluar "
            f"con un horizonte de {h} días."
        )

    # Todos los candidatos se evalúan bajo el mismo protocolo.
    candidatos = {lb.nombre: (lambda lb: lambda y, k: lb.pronosticar(y, k))(lb) for lb in baselines.catalogo_por_defecto()}
    candidatos["gradient_boosting"] = _pronosticador_gbr(df)

    ranking = evaluation.comparar_candidatos(serie, candidatos, h, N_VENTANAS_EVALUACION)
    por_nombre = {e["nombre"]: e for e in ranking}

    eval_modelo = por_nombre.get("gradient_boosting", {"evaluado": False})
    # La tesis fija el naive estacional como la referencia a batir (cap. 2.5.1).
    eval_referencia = por_nombre.get("naive_estacional", {})

    volumen_medio = float(np.mean(np.abs(serie[-h:]))) or 1.0
    decision = evaluation.decidir_publicacion(eval_modelo, eval_referencia, volumen_medio)

    version = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    promedio = eval_modelo.get("promedio", {}) if eval_modelo.get("evaluado") else {}

    ruta_artefacto = None
    if decision["publicar"]:
        # Reentrenamiento final con todo el histórico: el modelo que se publica ve
        # más datos que el evaluado, práctica habitual, pero las métricas
        # registradas son las de la validación, no las de este ajuste.
        modelo_final = GradientBoostingRegressor(**HIPERPARAMETROS)
        modelo_final.fit(feats[FEATURE_COLUMNS], feats["total"])
        ruta_artefacto = _guardar_artefacto(modelo_final, version)

    mejor = next((e["nombre"] for e in ranking if e.get("evaluado")), None)

    run = models.ModelRun(
        algoritmo="GradientBoostingRegressor" if decision["publicar"] else f"no_publicado (mejor: {mejor})",
        version=version,
        mase=round(promedio["mase"], 4) if promedio.get("mase") is not None else None,
        wape=round(promedio["wape"], 2) if promedio.get("wape") is not None else None,
        # ModelRun no tiene columnas para el detalle y el proyecto aún no usa
        # migraciones, así que la evaluación completa se guarda aquí.
        parametros_json=json.dumps(
            {
                "hiperparametros": HIPERPARAMETROS,
                "protocolo": {
                    "validacion": "origen_movil",
                    "horizonte": h,
                    "n_ventanas": eval_modelo.get("n_ventanas"),
                    "periodo_estacional": metrics.PERIODO_ESTACIONAL,
                },
                "metricas_modelo": promedio,
                "decision": decision,
                "ranking": [
                    {"nombre": e["nombre"], "mase": e.get("promedio", {}).get("mase"),
                     "wape": e.get("promedio", {}).get("wape"), "evaluado": e.get("evaluado", False),
                     "motivo": e.get("motivo")}
                    for e in ranking
                ],
                "artefacto": ruta_artefacto,
            },
            default=str,
        ),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    return schemas.RetrainResponse(
        model_run_id=run.id,
        algoritmo=run.algoritmo,
        version=run.version,
        mase=run.mase,
        wape=run.wape,
        mejora_vs_baseline_pct=decision.get("mejora_pct"),
        publicado=decision["publicar"],
        motivo=decision["motivo"],
        mejor_candidato=mejor,
    )


def estado_del_modelo(db: Session) -> schemas.ModelStatusResponse:
    """Describe el último entrenamiento registrado, publicado o no (RF-09).

    La pantalla de pronóstico solo conocía el resultado del botón Recalibrar y
    mostraba "Sin entrenar" al abrirse aunque existiera un modelo publicado.
    """
    run = db.query(models.ModelRun).order_by(models.ModelRun.id.desc()).first()
    if run is None:
        return schemas.ModelStatusResponse(entrenado=False, publicado=False)

    detalle = {}
    if run.parametros_json:
        try:
            detalle = json.loads(run.parametros_json)
        except ValueError:
            detalle = {}
    decision = detalle.get("decision") or {}
    publicado = decision["publicar"] if "publicar" in decision else not run.algoritmo.startswith("no_publicado")

    return schemas.ModelStatusResponse(
        entrenado=True,
        publicado=bool(publicado),
        model_run_id=run.id,
        algoritmo=run.algoritmo,
        version=run.version,
        fecha=run.fecha,
        mase=run.mase,
        wape=run.wape,
        mejora_vs_baseline_pct=decision.get("mejora_pct"),
        motivo=decision.get("motivo"),
    )


def _cargar_modelo():
    if not os.path.exists(MODEL_PATH):
        return None
    return joblib.load(MODEL_PATH)


def _predecir_recursivo(modelo, df_hist: pd.DataFrame, dias: int) -> List[Tuple[pd.Timestamp, float]]:
    """Predice día a día realimentando los rezagos con sus propias predicciones.

    Recibe el modelo como parámetro (en vez de cargarlo de disco) para que la
    validación de origen móvil pueda evaluar un modelo reentrenado en cada
    ventana sin tocar el artefacto publicado.
    """
    resultados: List[Tuple[pd.Timestamp, float]] = []
    if df_hist.empty:
        return resultados

    ultima_fecha = df_hist["fecha"].max()
    historial = df_hist[["fecha", "total"]].copy()

    for i in range(1, dias + 1):
        fecha = ultima_fecha + timedelta(days=i)
        serie = historial["total"]

        fila = {"fecha": fecha}
        fila.update(cf.features_dict(fecha))
        fila["lag_1"] = float(serie.iloc[-1])
        fila["lag_7"] = float(serie.iloc[-7]) if len(serie) >= 7 else float(serie.iloc[-1])
        fila["lag_14"] = float(serie.iloc[-14]) if len(serie) >= 14 else float(serie.iloc[-1])
        fila["lag_30"] = float(serie.iloc[-30]) if len(serie) >= 30 else float(serie.iloc[-1])
        fila["media_movil_7"] = float(serie.tail(7).mean())
        fila["media_movil_30"] = float(serie.tail(30).mean())

        X = pd.DataFrame([fila])[FEATURE_COLUMNS]
        pred = max(0.0, float(modelo.predict(X)[0]))
        resultados.append((fecha, round(pred, 2)))

        historial = pd.concat([historial, pd.DataFrame([{"fecha": fecha, "total": pred}])], ignore_index=True)

    return resultados


def _pronosticar_dias(df_hist: pd.DataFrame, dias: int) -> List[Tuple[pd.Timestamp, float]]:
    """Pronostica día a día hacia adelante usando el modelo publicado."""
    modelo = _cargar_modelo()
    resultados: List[Tuple[pd.Timestamp, float]] = []

    if df_hist.empty:
        return resultados

    ultima_fecha = df_hist["fecha"].max()

    if modelo is None:
        # Sin modelo entrenado todavía: promedio móvil reciente ajustado por estacionalidad conocida.
        base = df_hist["total"].tail(28).mean()
        for i in range(1, dias + 1):
            fecha = ultima_fecha + timedelta(days=i)
            factor = 1.0
            if cf.es_temporada_diciembre(fecha):
                factor = 1.35
            elif cf.es_semana_bono14(fecha):
                factor = 1.25
            elif cf.es_caravana_del_zorro(fecha):
                factor = 1.2
            resultados.append((fecha, round(float(base * factor), 2)))
        return resultados

    return _predecir_recursivo(modelo, df_hist, dias)


def proyeccion_proximo_mes(db: Session) -> Tuple[float, Optional[float]]:
    df = _ventas_diarias(db)
    if df.empty:
        return 0.0, None
    pronostico = _pronosticar_dias(df, 30)
    total = round(sum(v for _, v in pronostico), 2)

    modelo = _cargar_modelo()
    ultimo_run = db.query(models.ModelRun).order_by(models.ModelRun.fecha.desc()).first()
    confianza = None
    if modelo is not None and ultimo_run and ultimo_run.wape is not None:
        confianza = round(max(0.0, min(99.0, 100 - ultimo_run.wape)), 1)
    return total, confianza


def tendencia_mensual(db: Session, meses: int = 12) -> List[schemas.TrendPoint]:
    df = _ventas_diarias(db)
    if df.empty:
        return []

    df = df.copy()
    df["periodo"] = df["fecha"].dt.to_period("M")
    real_mensual = df.groupby("periodo")["total"].sum().tail(meses)

    pronostico = _pronosticar_dias(df, 30)
    df_pron = pd.DataFrame(pronostico, columns=["fecha", "total"])
    df_pron["periodo"] = pd.to_datetime(df_pron["fecha"]).dt.to_period("M")
    proyectado_mensual = df_pron.groupby("periodo")["total"].sum()

    periodos = list(real_mensual.index) + [p for p in proyectado_mensual.index if p not in real_mensual.index]
    puntos: List[schemas.TrendPoint] = []
    for periodo in periodos:
        puntos.append(
            schemas.TrendPoint(
                fecha=str(periodo),
                real=round(float(real_mensual[periodo]), 2) if periodo in real_mensual.index else None,
                proyectado=round(float(proyectado_mensual[periodo]), 2) if periodo in proyectado_mensual.index else None,
            )
        )
    return puntos


def serie_historica_y_pronostico(db: Session, horizonte: int = 30) -> List[schemas.ForecastPoint]:
    df = _ventas_diarias(db)
    puntos: List[schemas.ForecastPoint] = []
    if df.empty:
        return puntos

    historico = df.tail(60)
    for _, fila in historico.iterrows():
        puntos.append(schemas.ForecastPoint(fecha=fila["fecha"].strftime("%Y-%m-%d"), real=round(float(fila["total"]), 2)))

    pronostico = _pronosticar_dias(df, horizonte)
    for fecha, valor in pronostico:
        margen = valor * 0.15
        puntos.append(
            schemas.ForecastPoint(
                fecha=fecha.strftime("%Y-%m-%d"),
                pronostico=valor,
                intervalo_inf=round(max(0.0, valor - margen), 2),
                intervalo_sup=round(valor + margen, 2),
            )
        )
    return puntos


def senales_por_producto(db: Session, dias_recientes: int = 14) -> List[schemas.ProductSignal]:
    """Compara ventas recientes vs. el periodo previo por producto para detectar alta/baja demanda."""
    hoy = datetime.utcnow()
    inicio_reciente = hoy - timedelta(days=dias_recientes)
    inicio_previo = inicio_reciente - timedelta(days=dias_recientes)

    def _ventas_por_producto(desde: datetime, hasta: datetime) -> dict:
        filas = (
            db.query(models.SaleItem.product_id, func.sum(models.SaleItem.cantidad))
            .join(models.Sale)
            .filter(models.Sale.fecha_hora >= desde, models.Sale.fecha_hora < hasta)
            .group_by(models.SaleItem.product_id)
            .all()
        )
        return {pid: cant for pid, cant in filas}

    recientes = _ventas_por_producto(inicio_reciente, hoy)
    previas = _ventas_por_producto(inicio_previo, inicio_reciente)

    productos = {p.id: p for p in db.query(models.Product).filter(models.Product.activo == True).all()}  # noqa: E712

    señales: List[schemas.ProductSignal] = []
    for pid, cant_reciente in recientes.items():
        producto = productos.get(pid)
        if not producto:
            continue
        cant_previa = previas.get(pid, 0)
        if cant_previa == 0:
            magnitud = 100.0 if cant_reciente > 0 else 0.0
        else:
            magnitud = ((cant_reciente - cant_previa) / cant_previa) * 100

        if abs(magnitud) < 15:
            continue

        señales.append(
            schemas.ProductSignal(
                product_id=pid,
                nombre=producto.nombre,
                categoria=producto.categoria,
                tendencia="alta_demanda" if magnitud > 0 else "baja_demanda",
                magnitud_pct=round(magnitud, 1),
            )
        )

    señales.sort(key=lambda s: abs(s.magnitud_pct), reverse=True)
    return señales[:8]
