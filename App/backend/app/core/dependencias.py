"""Dependencias HTTP transversales, sin conocimiento de capacidades."""

from __future__ import annotations

from collections.abc import AsyncIterator
from ipaddress import ip_address
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
    candidato = reenviado.split(",")[0].strip() if reenviado else None
    if candidato is None and request.client:
        candidato = request.client.host
    if not candidato:
        return None
    try:
        return str(ip_address(candidato))
    except ValueError:
        return None


IpCliente = Annotated[str | None, Depends(ip_cliente)]
