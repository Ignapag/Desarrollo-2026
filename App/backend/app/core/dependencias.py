"""Dependencias de FastAPI compartidas por los modulos."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request

from app.core.db import UnidadDeTrabajo, conexion


async def obtener_uow() -> AsyncIterator[UnidadDeTrabajo]:
    """Una transaccion por request: commit al terminar, rollback si hay error."""
    async with conexion() as conn:
        yield UnidadDeTrabajo(conn)


UoW = Annotated[UnidadDeTrabajo, Depends(obtener_uow)]


def ip_cliente(request: Request) -> str | None:
    reenviado = request.headers.get("x-forwarded-for")
    if reenviado:
        return reenviado.split(",")[0].strip()
    return request.client.host if request.client else None


IpCliente = Annotated[str | None, Depends(ip_cliente)]
