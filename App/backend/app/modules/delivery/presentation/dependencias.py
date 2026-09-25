"""Composicion del modulo de delivery.

Las dependencias especificas de una capacidad viven junto a esa capacidad.
``app.core.dependencias`` conserva solamente piezas transversales como la
unidad de trabajo y la IP del cliente.
"""

from typing import Annotated

from fastapi import Depends

from app.core.dependencias import UoW
from app.modules.delivery.application.servicio_delivery import ServicioDelivery
from app.modules.delivery.infrastructure.repositorio_sql import RepositorioDeliverySQL


def obtener_servicio_delivery(uow: UoW) -> ServicioDelivery:
    return ServicioDelivery(uow, RepositorioDeliverySQL(uow))


ServicioDeliveryDep = Annotated[ServicioDelivery, Depends(obtener_servicio_delivery)]
