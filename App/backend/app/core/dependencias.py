"""Dependencias de FastAPI compartidas por los modulos."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request

from app.core.db import UnidadDeTrabajo, conexion
from app.modules.delivery.application.servicio_delivery import ServicioDelivery
from app.modules.delivery.infrastructure.repositorio_sql import RepositorioDeliverySQL


async def obtener_uow() -> AsyncIterator[UnidadDeTrabajo]:
    """Una transaccion por request: commit al terminar, rollback si hay error."""
    async with conexion() as conn:
        yield UnidadDeTrabajo(conn)


UoW = Annotated[UnidadDeTrabajo, Depends(obtener_uow)]


def obtener_servicio_delivery(uow: UoW) -> ServicioDelivery:
    return ServicioDelivery(uow, RepositorioDeliverySQL(uow))


ServicioDeliveryDep = Annotated[ServicioDelivery, Depends(obtener_servicio_delivery)]


def ip_cliente(request: Request) -> str | None:
    reenviado = request.headers.get("x-forwarded-for")
    if reenviado:
        return reenviado.split(",")[0].strip()
    return request.client.host if request.client else None


IpCliente = Annotated[str | None, Depends(ip_cliente)]

# Nota: las guardas de autenticacion y rol viven en el modulo de Usuarios y
# Seguridad (EDT 1.8), que esta a cargo de otro integrante. Cuando ese modulo
# se integre, la dependencia de rol se declara ANTES que UoW en la firma del
# endpoint: FastAPI resuelve en orden, y asi un request sin sesion se rechaza
# sin pedir una conexion a la base.
