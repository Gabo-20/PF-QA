from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..deps import get_current_user, get_db
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user or not user.activo or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    token = create_access_token({"sub": str(user.id)})
    return schemas.TokenResponse(access_token=token, rol=user.rol.value, nombre=user.nombre)


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.put("/me/password", response_model=schemas.UserOut)
def cambiar_mi_password(
    payload: schemas.PasswordChange,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Cambia la contraseña propia. Disponible para cualquier rol.

    Exige la contraseña actual: sin eso, un token robado permitiria al atacante
    apoderarse de la cuenta cambiando la clave.
    """
    if not verify_password(payload.password_actual, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual no es correcta",
        )
    if payload.password_nueva == payload.password_actual:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña nueva debe ser distinta de la actual",
        )

    current_user.password_hash = hash_password(payload.password_nueva)
    db.commit()
    db.refresh(current_user)
    return current_user
