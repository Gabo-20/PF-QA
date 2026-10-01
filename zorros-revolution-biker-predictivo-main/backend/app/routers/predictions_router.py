from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import schemas
from ..deps import get_db, require_role
from ..ml import forecasting, reorder, series_profile

router = APIRouter(prefix="/predictions", tags=["predicciones"])


@router.get("/forecast", response_model=List[schemas.ForecastPoint])
def forecast(
    # Acotado: la predicción es recursiva y sin límite un horizonte grande bloquea
    # el worker (cada paso reconstruye el DataFrame del historial).
    horizonte: int = Query(30, ge=1, le=180),
    db: Session = Depends(get_db),
    _=Depends(require_role("admin")),
):
    return forecasting.serie_historica_y_pronostico(db, horizonte)


@router.get("/signals", response_model=List[schemas.ProductSignal])
def signals(db: Session = Depends(get_db), _=Depends(require_role("admin"))):
    return forecasting.senales_por_producto(db)


@router.post("/retrain", response_model=schemas.RetrainResponse)
def retrain(db: Session = Depends(get_db), _=Depends(require_role("admin"))):
    try:
        return forecasting.entrenar_modelo(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/model", response_model=schemas.ModelStatusResponse)
def model_status(db: Session = Depends(get_db), _=Depends(require_role("admin"))):
    """Último entrenamiento registrado, para mostrarlo al abrir la pantalla."""
    return forecasting.estado_del_modelo(db)


@router.get("/recommendations", response_model=List[schemas.RecommendationOut])
def recommendations(db: Session = Depends(get_db), _=Depends(require_role("admin"))):
    return reorder.generar_recomendaciones(db)


@router.get("/series-profile", response_model=schemas.SeriesProfileResponse)
def series_profile_endpoint(db: Session = Depends(get_db), _=Depends(require_role("admin"))):
    """Perfil de intermitencia de cada serie de demanda (cap. 2.2.3 de la tesis).

    Trabaja sobre unidades por producto y día, no sobre el total en quetzales, y
    clasifica cada producto segun Syntetos-Boylan-Croston para decidir que
    estrategia de pronostico le corresponde.
    """
    perfiles = series_profile.perfilar_catalogo(db)
    return {"resumen": series_profile.resumir(perfiles), "series": perfiles}
