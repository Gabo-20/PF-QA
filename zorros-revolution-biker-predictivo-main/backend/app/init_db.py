"""Crea el esquema una sola vez, antes de que arranquen los workers.

`main.py` tambien llama a `create_all`, pero lo hace al importarse: con varios
workers de Gunicorn los procesos entran a la vez y, sobre PostgreSQL, uno falla
al crear los tipos ENUM por duplicado ("duplicate key ... pg_type_typname_nsp_index").
`create_all` usa checkfirst, que es un comprobar-luego-actuar y no protege de la
carrera.

Ejecutando esto antes de Gunicorn, el esquema ya existe cuando los workers
importan la app, y su `create_all` queda en una comprobacion de solo lectura.
"""
from .database import Base, engine
from . import models  # noqa: F401  -- registra las tablas en el metadata


def main() -> None:
    Base.metadata.create_all(bind=engine)
    print("Esquema verificado/creado correctamente.")


if __name__ == "__main__":
    main()
