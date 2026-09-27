"""Composicion del modulo de productos."""

from typing import Annotated

from fastapi import Depends

from app.core.dependencias import UoW
from app.modules.productos.application.servicio_productos import ServicioProductos
from app.modules.productos.infrastructure.repositorio_sql import RepositorioProductosSQL


def obtener_servicio_productos(uow: UoW) -> ServicioProductos:
    return ServicioProductos(RepositorioProductosSQL(uow))


ServicioProductosDep = Annotated[ServicioProductos, Depends(obtener_servicio_productos)]
