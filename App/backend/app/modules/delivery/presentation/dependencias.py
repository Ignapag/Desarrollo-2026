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
from app.modules.pedidos.presentation.dependencias import obtener_servicio_pedidos


def obtener_servicio_delivery(uow: UoW) -> ServicioDelivery:
    """Arma el servicio de delivery con su repositorio y el servicio de pedidos.

    El servicio de pedidos es la autoridad sobre las transiciones de estado del pedido (en camino,
    entregado, listo).
    """
    return ServicioDelivery(uow, RepositorioDeliverySQL(uow), obtener_servicio_pedidos(uow))


ServicioDeliveryDep = Annotated[ServicioDelivery, Depends(obtener_servicio_delivery)]
