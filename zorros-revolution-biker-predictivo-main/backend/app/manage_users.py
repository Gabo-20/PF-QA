"""Gestion de usuarios desde la linea de comandos.

Es la via de recuperacion: si se pierde la contraseña del ultimo administrador,
la interfaz web no ofrece ninguna forma de recuperar el acceso. Este modulo si.

Uso (dentro del contenedor):

    docker compose exec api python -m app.manage_users listar
    docker compose exec api python -m app.manage_users password admin@ejemplo.com
    docker compose exec api python -m app.manage_users password admin@ejemplo.com --generar
    docker compose exec api python -m app.manage_users crear-admin nuevo@ejemplo.com "Nombre Real"
    docker compose exec api python -m app.manage_users rol usuario@ejemplo.com admin

Las contraseñas nunca se pasan como argumento: o se piden de forma interactiva
(sin eco en pantalla) o se generan al azar. Un argumento quedaria registrado en
el historial del shell y en la lista de procesos.
"""
import argparse
import getpass
import secrets
import string
import sys

from . import models
from .database import SessionLocal
from .schemas import validar_password
from .security import hash_password


def _generar(longitud: int = 16) -> str:
    alfabeto = string.ascii_letters + string.digits
    while True:
        clave = "".join(secrets.choice(alfabeto) for _ in range(longitud))
        if any(c.isalpha() for c in clave) and any(c.isdigit() for c in clave):
            return clave


def _pedir_password() -> str:
    if not sys.stdin.isatty():
        print("Entrada no interactiva: usa --generar para crear una al azar.", file=sys.stderr)
        sys.exit(2)
    while True:
        clave = getpass.getpass("Contraseña nueva: ")
        try:
            validar_password(clave)
        except ValueError as exc:
            print(f"  {exc}", file=sys.stderr)
            continue
        if clave != getpass.getpass("Confirmar: "):
            print("  No coinciden.", file=sys.stderr)
            continue
        return clave


def _buscar(db, email: str) -> models.User:
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        print(f"No existe ningun usuario con el correo {email}", file=sys.stderr)
        sys.exit(1)
    return user


def cmd_listar(db, _args) -> None:
    usuarios = db.query(models.User).order_by(models.User.nombre).all()
    if not usuarios:
        print("No hay usuarios registrados.")
        return
    print(f"{'id':>4}  {'rol':<8} {'activo':<7} {'correo':<38} nombre")
    for u in usuarios:
        print(f"{u.id:>4}  {u.rol.value:<8} {'si' if u.activo else 'no':<7} {u.email:<38} {u.nombre}")


def cmd_password(db, args) -> None:
    user = _buscar(db, args.email)
    clave = _generar() if args.generar else _pedir_password()
    user.password_hash = hash_password(clave)
    db.commit()
    print(f"Contraseña actualizada para {user.email}")
    if args.generar:
        print(f"  {clave}")
        print("  Anotala: solo queda su hash en la base de datos.")


def cmd_crear_admin(db, args) -> None:
    if db.query(models.User).filter(models.User.email == args.email).first():
        print(f"Ya existe un usuario con el correo {args.email}", file=sys.stderr)
        sys.exit(1)
    clave = _generar() if args.generar else _pedir_password()
    db.add(
        models.User(
            nombre=args.nombre,
            email=args.email,
            password_hash=hash_password(clave),
            rol=models.RolUsuario.admin,
            activo=True,
        )
    )
    db.commit()
    print(f"Administrador creado: {args.email}")
    if args.generar:
        print(f"  {clave}")


def cmd_rol(db, args) -> None:
    user = _buscar(db, args.email)
    nuevo = models.RolUsuario(args.rol)

    if user.rol == models.RolUsuario.admin and nuevo != models.RolUsuario.admin:
        otros = (
            db.query(models.User)
            .filter(
                models.User.rol == models.RolUsuario.admin,
                models.User.activo.is_(True),
                models.User.id != user.id,
            )
            .count()
        )
        if otros == 0:
            print("Es el ultimo administrador activo: no se puede degradar.", file=sys.stderr)
            sys.exit(1)

    user.rol = nuevo
    db.commit()
    print(f"{user.email} ahora tiene el rol {nuevo.value}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.manage_users", description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("listar", help="Lista los usuarios registrados")

    p_pass = sub.add_parser("password", help="Establece la contraseña de un usuario")
    p_pass.add_argument("email")
    p_pass.add_argument("--generar", action="store_true", help="Genera una al azar en vez de pedirla")

    p_admin = sub.add_parser("crear-admin", help="Crea un nuevo administrador")
    p_admin.add_argument("email")
    p_admin.add_argument("nombre")
    p_admin.add_argument("--generar", action="store_true")

    p_rol = sub.add_parser("rol", help="Cambia el rol de un usuario")
    p_rol.add_argument("email")
    p_rol.add_argument("rol", choices=[r.value for r in models.RolUsuario])

    args = parser.parse_args()
    comandos = {
        "listar": cmd_listar,
        "password": cmd_password,
        "crear-admin": cmd_crear_admin,
        "rol": cmd_rol,
    }

    db = SessionLocal()
    try:
        comandos[args.comando](db, args)
    finally:
        db.close()


if __name__ == "__main__":
    main()
