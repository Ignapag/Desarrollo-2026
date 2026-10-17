"""Configuracion comun de las pruebas.

Importar app.core.db ajusta el event loop de Windows, necesario para que
psycopg funcione en modo async (ver configurar_event_loop).

Las pruebas con base usan ``tests/soporte_bd.py``: solo corren contra una
PostgreSQL local y descartable, salvo opt-in explicito.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio

from app.core.db import UnidadDeTrabajo, configurar_event_loop
from tests.soporte_bd import conectar_o_omitir

configurar_event_loop()


@pytest_asyncio.fixture
async def uow() -> AsyncIterator[UnidadDeTrabajo]:
    """Unidad de trabajo sobre una transaccion que siempre se revierte."""
    conn = await conectar_o_omitir()
    try:
        yield UnidadDeTrabajo(conn)
    finally:
        await conn.rollback()
        await conn.close()
