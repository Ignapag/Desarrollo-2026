"""Acceso a PostgreSQL para las pruebas de repositorios, SQL y HTTP.

Las pruebas con base escriben datos: algunas revierten su transaccion, otras
confirman y limpian (HTTP, concurrencia). Por eso solo corren contra una base
local y descartable. Si ``DATABASE_URL`` apunta a otro host (por ejemplo la
base compartida del grupo en ``App/.env``), se omiten con el motivo, salvo
que se defina ``MONU_PERMITIR_BD_REMOTA=1`` de forma explicita.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from app.core.config import settings
from app.core.db import UnidadDeTrabajo

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


@asynccontextmanager
async def mantenimiento_pruebas(uow: UnidadDeTrabajo) -> AsyncIterator[None]:
    """Permite purgar solo los datos de una prueba en su base local explícita.

    Desactiva únicamente las guardas de conservación, conservando las FK, cascadas y
    auditoría. El bloque debe ejecutarse cuando las otras conexiones ya terminaron;
    no admite commits/rollbacks internos. Un savepoint restaura datos y modos si falla.
    Nunca se usa durante el ejercicio de un caso de negocio ni desde la aplicación.
    """
    configurada = os.environ.get("DATABASE_URL")
    if not configurada:
        raise RuntimeError("La limpieza requiere DATABASE_URL explícita de una base descartable")
    for parametros in (conninfo_to_dict(configurada), conninfo_to_dict(uow.conn.info.dsn)):
        destinos = _destinos(parametros)
        if parametros.get("service") or os.environ.get("PGSERVICE") or any(
            not host.startswith("/") and host not in HOSTS_DESCARTABLES for host in destinos
        ):
            raise RuntimeError("La limpieza administrativa de pruebas no admite bases remotas")

    async with uow.conn.transaction():
        guardas = await uow.todos(
            "SELECT c.relname AS tabla,t.tgname AS trigger,t.tgenabled AS modo "
            "FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND NOT t.tgisinternal "
            "AND starts_with(t.tgname::text,'monu_conservar_') ORDER BY c.relname,t.tgname"
        )
        contexto = await uow.uno(
            "SELECT current_setting('monu.usuario_id',true) AS usuario, "
            "current_setting('monu.ip',true) AS ip, "
            "current_setting('monu.origen',true) AS origen, "
            "current_setting('monu.identificador_operacion',true) AS identificador"
        )
        await uow.ejecutar(
            "SELECT set_config('monu.usuario_id','',true),set_config('monu.ip','',true),"
            "set_config('monu.origen','MANTENIMIENTO_PRUEBAS',true),"
            "set_config('monu.identificador_operacion',%s,true)", (str(uuid4()),),
        )
        for guarda in guardas:
            await uow.conn.execute(sql.SQL("ALTER TABLE {} DISABLE TRIGGER {}").format(
                sql.Identifier("public", guarda["tabla"]), sql.Identifier(guarda["trigger"]),
            ))
        yield
        modos = {"O": "ENABLE", "D": "DISABLE", "R": "ENABLE REPLICA", "A": "ENABLE ALWAYS"}
        for guarda in guardas:
            await uow.conn.execute(sql.SQL("ALTER TABLE {} {} TRIGGER {}").format(
                sql.Identifier("public", guarda["tabla"]), sql.SQL(modos[guarda["modo"]]),
                sql.Identifier(guarda["trigger"]),
            ))
        actor = contexto["usuario"] or ""
        if actor and not await uow.valor(
            "SELECT EXISTS(SELECT 1 FROM usuario WHERE id=%s)", (actor,),
        ):
            actor = ""
        await uow.ejecutar(
            "SELECT set_config('monu.usuario_id',%s,true),set_config('monu.ip',%s,true),"
            "set_config('monu.origen',%s,true),set_config('monu.identificador_operacion',%s,true)",
            (actor, contexto["ip"] or "", contexto["origen"] or "",
             contexto["identificador"] or ""),
        )
