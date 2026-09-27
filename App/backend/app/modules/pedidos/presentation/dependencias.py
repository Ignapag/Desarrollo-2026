"""Composicion del modulo de pedidos."""

from typing import Annotated

from fastapi import Depends

from app.core.dependencias import UoW
from app.modules.pedidos.application.servicio_pedidos import ServicioPedidos
from app.modules.pedidos.infrastructure.repositorio_sql import RepositorioPedidosSQL
from app.modules.pedidos.infrastructure.stock import AdaptadorConsumoStock
from app.modules.stock.application.servicio_stock import ServicioStock
from app.modules.stock.infrastructure.repositorio_sql import RepositorioStockSQL


def obtener_servicio_pedidos(uow: UoW) -> ServicioPedidos:
    stock = AdaptadorConsumoStock(ServicioStock(RepositorioStockSQL(uow)))
    return ServicioPedidos(RepositorioPedidosSQL(uow), stock)


ServicioPedidosDep = Annotated[ServicioPedidos, Depends(obtener_servicio_pedidos)]
