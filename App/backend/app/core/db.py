"""Acceso a PostgreSQL con psycopg 3 y SQL directo (sin ORM).

Expone un pool asincrono y helpers para ejecutar consultas parametrizadas.
Toda consulta del sistema debe usar parametros (%s) y nunca interpolar
valores en el string SQL.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings

_pool: AsyncConnectionPool | None = None


async def abrir_pool() -> AsyncConnectionPool:
    """Abre el pool sin bloquear el arranque.

    Si PostgreSQL todavia no esta disponible, la API igual levanta y
    /api/salud informa el problema; el pool reintenta conectar solo. Cada
    request que necesite la base falla individualmente hasta que la
    conexion se restablece.
    """
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(
            conninfo=settings.database_url,
            min_size=settings.db_pool_min,
            max_size=settings.db_pool_max,
            timeout=settings.db_timeout_conexion,
            kwargs={"row_factory": dict_row},
            open=False,
        )
        await _pool.open(wait=False)
    return _pool


async def verificar_conexion(timeout: float | None = None) -> None:
    """Ejecuta un SELECT 1. Lanza excepcion si la base no responde."""
    espera = timeout if timeout is not None else settings.db_timeout_conexion
    async with pool().connection(timeout=espera) as conn, conn.cursor() as cur:
        await cur.execute("SELECT 1")
        await cur.fetchone()


async def cerrar_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("El pool de conexiones no esta inicializado")
    return _pool


@asynccontextmanager
async def conexion() -> AsyncIterator[AsyncConnection]:
    """Conexion con transaccion: commit al salir, rollback si hay excepcion."""
    async with pool().connection() as conn:
        yield conn


class UnidadDeTrabajo:
    """Envuelve una conexion/transaccion y ofrece los helpers de consulta.

    Se inyecta en los repositorios para que un caso de uso pueda agrupar
    varias escrituras en una sola transaccion (por ejemplo: confirmar un
    pedido, descontar stock y registrar auditoria).
    """

    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def uno(self, sql: str, parametros: Sequence[Any] | None = None) -> dict | None:
        async with self.conn.cursor() as cur:
            await cur.execute(sql, parametros)
            return await cur.fetchone()

    async def todos(self, sql: str, parametros: Sequence[Any] | None = None) -> list[dict]:
        async with self.conn.cursor() as cur:
            await cur.execute(sql, parametros)
            return list(await cur.fetchall())

    async def valor(self, sql: str, parametros: Sequence[Any] | None = None) -> Any:
        fila = await self.uno(sql, parametros)
        if fila is None:
            return None
        return next(iter(fila.values()))

    async def ejecutar(self, sql: str, parametros: Sequence[Any] | None = None) -> int:
        async with self.conn.cursor() as cur:
            await cur.execute(sql, parametros)
            return cur.rowcount
