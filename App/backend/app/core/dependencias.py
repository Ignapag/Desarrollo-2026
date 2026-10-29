"""Dependencias HTTP transversales, sin conocimiento de capacidades."""

from __future__ import annotations

from collections.abc import AsyncIterator
from ipaddress import ip_address
from typing import Annotated

from fastapi import Depends, Request

from app.core.db import UnidadDeTrabajo, conexion


async def obtener_uow(request: Request) -> AsyncIterator[UnidadDeTrabajo]:
    """Una transaccion por request: commit al terminar, rollback si hay error."""
    async with conexion() as conn:
        uow = UnidadDeTrabajo(conn)
        origen = "chat_demo" if request.url.path.startswith("/api/chat-demo/") else "http"
        await uow.configurar_auditoria(origen=origen, ip=ip_cliente(request))
        yield uow


UoW = Annotated[UnidadDeTrabajo, Depends(obtener_uow)]


def ip_cliente(request: Request) -> str | None:
    """Obtiene la IP real del cliente para auditoría.

    Prioriza el primer valor de ``X-Forwarded-For`` (detrás de un proxy) y si no, usa la IP de la
    conexión. Devuelve ``None`` si el valor no es una IP válida.
    """
    reenviado = request.headers.get("x-forwarded-for")
    candidato = reenviado.split(",")[0].strip() if reenviado else None
    if candidato is None and request.client:
        candidato = request.client.host
    if not candidato:
        return None
    # Normaliza la IP y descarta valores mal formados en el encabezado.
    try:
        return str(ip_address(candidato))
    except ValueError:
        return None


IpCliente = Annotated[str | None, Depends(ip_cliente)]
