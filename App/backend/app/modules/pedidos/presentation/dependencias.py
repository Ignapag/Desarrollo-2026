"""Composicion del modulo de pedidos."""

from typing import Annotated

from fastapi import Depends

from app.core.dependencias import UoW
from app.modules.pedidos.application.servicio_pedidos import ServicioPedidos
from app.modules.pedidos.infrastructure.repositorio_sql import RepositorioPedidosSQL
from app.modules.pedidos.infrastructure.stock import AdaptadorConsumoStock
from app.modules.stock.presentation.dependencias import obtener_servicio_stock


def obtener_servicio_pedidos(uow: UoW) -> ServicioPedidos:
    # Stock comparte la unidad de trabajo: pedido y consumo confirman juntos.
    stock = AdaptadorConsumoStock(obtener_servicio_stock(uow))
    return ServicioPedidos(RepositorioPedidosSQL(uow), stock)


ServicioPedidosDep = Annotated[ServicioPedidos, Depends(obtener_servicio_pedidos)]
