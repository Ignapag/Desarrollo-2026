"""Acceso a PostgreSQL con psycopg 3 y SQL directo (sin ORM).

Expone un pool asincrono y helpers para ejecutar consultas parametrizadas.
Toda consulta del sistema debe usar parametros (%s) y nunca interpolar
valores en el string SQL.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from ipaddress import ip_address
from typing import Any
from uuid import uuid4

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings

_pool: AsyncConnectionPool | None = None


def configurar_event_loop() -> None:
    """En Windows, psycopg async no funciona con el event loop por defecto.

    Python usa ProactorEventLoop en Windows y psycopg necesita
    SelectorEventLoop; sin esto, cualquier consulta falla con
    InterfaceError. Se llama al importar este modulo para que valga tanto
    para la API como para los scripts y las pruebas.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


configurar_event_loop()


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
    """Cierra el pool de conexiones al apagar la API, si estaba abierto."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> AsyncConnectionPool:
    """Devuelve el pool global; falla si todavía no se abrió con ``abrir_pool``."""
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

    def __init__(
        self, conn: AsyncConnection, *, origen: str | None = None,
        identificador_operacion: str | None = None,
    ) -> None:
        """Recibe la conexión (con su transacción) que comparten los repositorios."""
        self.conn = conn
        # El worker puede declarar el origen sin abrir una transacción hasta su
        # primera consulta. La identidad nunca se hereda de otra unidad de trabajo.
        self._contexto_pendiente = (
            ("", "", origen, identificador_operacion or str(uuid4())) if origen else None
        )

    async def configurar_auditoria(
        self, *, origen: str, ip: str | None = None,
        identificador_operacion: str | None = None,
    ) -> None:
        """Instala contexto local a esta transacción, inicialmente sin actor.

        PostgreSQL lo descarta al confirmar o revertir. No se guardan datos de
        usuario en una conexión de pool ni en un estado global de Python.
        """
        self._contexto_pendiente = (
            "", str(ip_address(ip)) if ip else "", origen,
            identificador_operacion or str(uuid4()),
        )
        await self._aplicar_contexto()

    async def atribuir_actor(self, usuario_id: int) -> None:
        """Atribuye escrituras posteriores a una identidad previamente validada."""
        if usuario_id <= 0:
            raise ValueError("El usuario de auditoría debe ser un identificador positivo")
        await self._aplicar_contexto()
        async with self.conn.cursor() as cur:
            await cur.execute(
                "SELECT set_config('monu.usuario_id', %s, true)", (str(usuario_id),),
            )

    async def _aplicar_contexto(self) -> None:
        """Configura solo los GUC pendientes, antes de cualquier SQL del caso de uso."""
        if self._contexto_pendiente is None:
            return
        async with self.conn.cursor() as cur:
            await cur.execute(
                """SELECT set_config('monu.usuario_id', %s, true),
                          set_config('monu.ip', %s, true),
                          set_config('monu.origen', %s, true),
                          set_config('monu.identificador_operacion', %s, true)""",
                self._contexto_pendiente,
            )
        self._contexto_pendiente = None

    async def uno(self, sql: str, parametros: Sequence[Any] | None = None) -> dict | None:
        """Ejecuta la consulta y devuelve la primera fila como dict, o ``None``."""
        await self._aplicar_contexto()
        async with self.conn.cursor() as cur:
            await cur.execute(sql, parametros)
            return await cur.fetchone()

    async def todos(self, sql: str, parametros: Sequence[Any] | None = None) -> list[dict]:
        """Ejecuta la consulta y devuelve todas las filas como lista de dicts."""
        await self._aplicar_contexto()
        async with self.conn.cursor() as cur:
            await cur.execute(sql, parametros)
            return list(await cur.fetchall())

    async def valor(self, sql: str, parametros: Sequence[Any] | None = None) -> Any:
        """Devuelve la primera columna de la primera fila (útil para COUNT, RETURNING id)."""
        fila = await self.uno(sql, parametros)
        if fila is None:
            return None
        return next(iter(fila.values()))

    async def ejecutar(self, sql: str, parametros: Sequence[Any] | None = None) -> int:
        """Ejecuta una sentencia de escritura y devuelve la cantidad de filas afectadas."""
        await self._aplicar_contexto()
        async with self.conn.cursor() as cur:
            await cur.execute(sql, parametros)
            return cur.rowcount
