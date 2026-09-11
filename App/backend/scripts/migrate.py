"""Ejecutor de migraciones SQL.

El stack no usa ORM, por lo tanto tampoco Alembic: las migraciones son
archivos .sql numerados en db/migrations que se aplican en orden y se
registran en la tabla schema_migrations.

Uso:
    python -m scripts.migrate            # aplica migraciones pendientes
    python -m scripts.migrate --seed     # aplica migraciones y carga db/seed.sql
    python -m scripts.migrate --status   # solo informa que falta aplicar
    python -m scripts.migrate --reset    # DESTRUCTIVO: recrea el schema public
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import psycopg

from app.core.config import settings


def _dir_db() -> Path:
    """Ubica el directorio db/ tanto en local como dentro del contenedor."""
    import os

    if (env := os.getenv("MONU_DB_DIR")):
        return Path(env)

    candidatos = [
        Path(__file__).resolve().parents[2] / "db",  # repo local: <raiz>/db
        Path(__file__).resolve().parents[1] / "db",  # backend/db (montaje docker)
        Path("/db"),
    ]
    for candidato in candidatos:
        if (candidato / "migrations").is_dir():
            return candidato
    return candidatos[0]


DIR_DB = _dir_db()
DIR_MIGRACIONES = DIR_DB / "migrations"
ARCHIVO_SEED = DIR_DB / "seed.sql"

TABLA_CONTROL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT        PRIMARY KEY,
    checksum    TEXT        NOT NULL,
    aplicada_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _migraciones() -> list[Path]:
    if not DIR_MIGRACIONES.exists():
        raise SystemExit(f"No existe el directorio de migraciones: {DIR_MIGRACIONES}")
    return sorted(DIR_MIGRACIONES.glob("*.sql"))


def _checksum(archivo: Path) -> str:
    return hashlib.sha256(archivo.read_bytes()).hexdigest()[:16]


def _aplicadas(conn: psycopg.Connection) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT version, checksum FROM schema_migrations")
        return {fila[0]: fila[1] for fila in cur.fetchall()}


def aplicar(conn: psycopg.Connection, *, solo_estado: bool = False) -> int:
    with conn.cursor() as cur:
        cur.execute(TABLA_CONTROL)
    conn.commit()

    ya_aplicadas = _aplicadas(conn)
    pendientes = 0

    for archivo in _migraciones():
        version = archivo.stem
        checksum = _checksum(archivo)

        if version in ya_aplicadas:
            if ya_aplicadas[version] != checksum:
                print(f"  [!] {version}: el archivo cambio despues de aplicarse "
                      f"(checksum {ya_aplicadas[version]} -> {checksum}). "
                      f"Crea una migracion nueva en lugar de editar esta.")
            continue

        pendientes += 1
        if solo_estado:
            print(f"  [ ] {version} (pendiente)")
            continue

        print(f"  [>] aplicando {version} ...")
        with conn.cursor() as cur:
            cur.execute(archivo.read_text(encoding="utf-8"))
            cur.execute(
                "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                (version, checksum),
            )
        conn.commit()
        print(f"  [x] {version} aplicada")

    if pendientes == 0:
        print("  Sin migraciones pendientes.")
    return pendientes


def sembrar(conn: psycopg.Connection) -> None:
    if not ARCHIVO_SEED.exists():
        print("  No hay archivo de seed.")
        return
    print("  [>] cargando datos de desarrollo (seed.sql) ...")
    with conn.cursor() as cur:
        cur.execute(ARCHIVO_SEED.read_text(encoding="utf-8"))
    conn.commit()
    print("  [x] seed cargado")


def es_base_local() -> bool:
    """True si el DSN apunta a esta maquina.

    El grupo comparte una unica base en la nube: un --reset contra ella
    borraria el trabajo de los seis. Por eso la operacion destructiva solo
    se permite en local, salvo que se pida explicitamente lo contrario.
    """
    host = settings.dsn_visible.split("/")[0].split(":")[0].lower()
    return host in {"localhost", "127.0.0.1", "::1", "db", ""}


def resetear(conn: psycopg.Connection) -> None:
    print("  [!] DROP SCHEMA public CASCADE")
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Migraciones SQL de Monu Burger")
    parser.add_argument("--seed", action="store_true", help="cargar datos de desarrollo")
    parser.add_argument("--status", action="store_true", help="solo informar pendientes")
    parser.add_argument("--reset", action="store_true", help="DESTRUCTIVO: recrea el schema")
    parser.add_argument(
        "--permitir-reset-remoto",
        action="store_true",
        help="habilita --reset contra una base que no es local (usar con MUCHO cuidado)",
    )
    args = parser.parse_args()

    print(f"Base de datos: {settings.dsn_visible}")

    if args.reset and not es_base_local() and not args.permitir_reset_remoto:
        print(
            "\n  [!] CANCELADO. El DSN no apunta a una base local, y el grupo comparte\n"
            "      una unica base: un --reset borraria el trabajo de todos.\n"
            "      Si de verdad es lo que queres, agrega --permitir-reset-remoto\n"
            "      y avisale al grupo ANTES de correrlo."
        )
        return 1

    with psycopg.connect(settings.database_url) as conn:
        if args.reset:
            destino = "LOCAL" if es_base_local() else "COMPARTIDA (remota)"
            confirmacion = input(
                f"Esto borra TODOS los datos de la base {destino}. "
                "Escribi 'BORRAR' para continuar: "
            )
            if confirmacion.strip() != "BORRAR":
                print("Cancelado.")
                return 1
            resetear(conn)

        aplicar(conn, solo_estado=args.status)

        if args.seed and not args.status:
            sembrar(conn)

    return 0


if __name__ == "__main__":
    sys.exit(main())
