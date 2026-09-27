"""Composicion del modulo de stock."""

from typing import Annotated

from fastapi import Depends

from app.core.dependencias import UoW
from app.modules.stock.application.servicio_stock import ServicioStock
from app.modules.stock.infrastructure.repositorio_sql import RepositorioStockSQL


def obtener_servicio_stock(uow: UoW) -> ServicioStock:
    return ServicioStock(RepositorioStockSQL(uow))


ServicioStockDep = Annotated[ServicioStock, Depends(obtener_servicio_stock)]
