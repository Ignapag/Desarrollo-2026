"""Composicion del modulo de reportes."""

from typing import Annotated

from fastapi import Depends

from app.core.dependencias import UoW
from app.modules.reportes.application.servicio_reportes import ServicioReportes
from app.modules.reportes.infrastructure.repositorio_sql import RepositorioReportesSQL
from app.modules.stock.application.servicio_stock import ServicioStock
from app.modules.stock.infrastructure.repositorio_sql import RepositorioStockSQL


def obtener_servicio_reportes(uow: UoW) -> ServicioReportes:
    return ServicioReportes(
        RepositorioReportesSQL(uow),
        ServicioStock(RepositorioStockSQL(uow)),
    )


ServicioReportesDep = Annotated[ServicioReportes, Depends(obtener_servicio_reportes)]
