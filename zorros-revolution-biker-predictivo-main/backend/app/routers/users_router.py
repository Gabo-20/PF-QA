from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..deps import get_db, require_role
from ..security import hash_password

router = APIRouter(prefix="/users", tags=["usuarios"])


def _obtener(db: Session, user_id: int) -> models.User:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


def _contar_admins_activos(db: Session, excluyendo: int | None = None) -> int:
    consulta = db.query(models.User).filter(
        models.User.rol == models.RolUsuario.admin,
        models.User.activo.is_(True),
    )
    if excluyendo is not None:
        consulta = consulta.filter(models.User.id != excluyendo)
    return consulta.count()


def _impedir_quedarse_sin_admin(db: Session, user: models.User) -> None:
    """Evita dejar el sistema sin ningún administrador activo.

    Sin esta guarda, desactivar o degradar al último admin deja la aplicación
    inaccesible: no queda nadie que pueda gestionar usuarios ni recuperar el
    acceso desde la interfaz.
    """
    es_admin_activo = user.rol == models.RolUsuario.admin and user.activo
    if es_admin_activo and _contar_admins_activos(db, excluyendo=user.id) == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede dejar el sistema sin ningún administrador activo",
        )


@router.get("", response_model=List[schemas.UserOut])
def list_users(db: Session = Depends(get_db), _=Depends(require_role("admin"))):
    return db.query(models.User).order_by(models.User.nombre).all()


@router.post("", response_model=schemas.UserOut, status_code=201)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db), _=Depends(require_role("admin"))):
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="El correo ya está registrado")
    user = models.User(
        nombre=payload.nombre,
        email=payload.email,
        password_hash=hash_password(payload.password),
        rol=models.RolUsuario(payload.rol),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}/rol", response_model=schemas.UserOut)
def cambiar_rol(
    user_id: int,
    payload: schemas.UserRolUpdate,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_role("admin")),
):
    """Cambia el rol de un usuario. El rol vive en la base, no en configuración."""
    user = _obtener(db, user_id)
    nuevo = models.RolUsuario(payload.rol)

    if user.id == actor.id and nuevo != models.RolUsuario.admin:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No puedes quitarte a ti mismo el rol de administrador",
        )
    if nuevo != models.RolUsuario.admin:
        _impedir_quedarse_sin_admin(db, user)

    user.rol = nuevo
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}/estado", response_model=schemas.UserOut)
def toggle_estado(
    user_id: int,
    payload: schemas.UserEstadoUpdate,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_role("admin")),
):
    user = _obtener(db, user_id)

    if user.id == actor.id and not payload.activo:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No puedes desactivar tu propia cuenta",
        )
    if not payload.activo:
        _impedir_quedarse_sin_admin(db, user)

    user.activo = payload.activo
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}/password", response_model=schemas.UserOut)
def restablecer_password(
    user_id: int,
    payload: schemas.PasswordReset,
    db: Session = Depends(get_db),
    _=Depends(require_role("admin")),
):
    """Un administrador establece la contraseña de otro usuario.

    Se guarda siempre el hash bcrypt: la contraseña en claro no se persiste ni
    se devuelve en la respuesta.
    """
    user = _obtener(db, user_id)
    user.password_hash = hash_password(payload.password_nueva)
    db.commit()
    db.refresh(user)
    return user
