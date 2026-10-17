"""Acceso a PostgreSQL para las pruebas de repositorios, SQL y HTTP.

Las pruebas con base escriben datos: algunas revierten su transaccion, otras
confirman y limpian (HTTP, concurrencia). Por eso solo corren contra una base
local y descartable. Si ``DATABASE_URL`` apunta a otro host (por ejemplo la
base compartida del grupo en ``App/.env``), se omiten con el motivo, salvo
que se defina ``MONU_PERMITIR_BD_REMOTA=1`` de forma explicita.
"""

from __future__ import annotations

import os

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from app.core.config import settings

VARIABLE_PERMITIR_REMOTA = "MONU_PERMITIR_BD_REMOTA"
# ``db`` es el servicio PostgreSQL de App/docker-compose.yml.
HOSTS_DESCARTABLES = frozenset({"localhost", "127.0.0.1", "::1", "db"})


def _destinos(parametros: dict) -> list[str]:
    """Hosts y direcciones a los que libpq podria conectarse con estos parametros."""
    destinos: list[str] = []
    for clave, variable in (("host", "PGHOST"), ("hostaddr", "PGHOSTADDR")):
        valor = parametros.get(clave) or os.environ.get(variable) or ""
        destinos.extend(item for item in str(valor).split(",") if item)
    return destinos


def motivo_para_omitir_bd() -> str | None:
    """Devuelve por que no se debe usar la base configurada, o None si se puede."""
    if os.environ.get(VARIABLE_PERMITIR_REMOTA) == "1":
        return None
    parametros = conninfo_to_dict(settings.database_url)
    if parametros.get("service") or os.environ.get("PGSERVICE"):
        remotos = ["un servicio de pg_service.conf"]
    else:
        remotos = [
            destino
            for destino in _destinos(parametros)
            if not destino.startswith("/") and destino not in HOSTS_DESCARTABLES
        ]
    if not remotos:
        return None
    return (
        f"DATABASE_URL apunta a {', '.join(remotos)}, que no es una base local descartable. "
        f"Configura una base de prueba o define {VARIABLE_PERMITIR_REMOTA}=1 a proposito."
    )


def exigir_base_descartable() -> None:
    motivo = motivo_para_omitir_bd()
    if motivo:
        pytest.skip(motivo)


async def conectar_o_omitir() -> psycopg.AsyncConnection:
    """Conexion nueva (sin autocommit) a la base de prueba, u omite la prueba."""
    exigir_base_descartable()
    try:
        return await psycopg.AsyncConnection.connect(
            settings.database_url, row_factory=dict_row, connect_timeout=10
        )
    except psycopg.OperationalError as exc:
        pytest.skip(f"Base no accesible: {exc.__class__.__name__}")
