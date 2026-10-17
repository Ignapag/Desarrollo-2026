"""Composicion del modulo de reportes."""

from typing import Annotated

from fastapi import Depends

from app.core.dependencias import UoW
from app.modules.reportes.application.servicio_reportes import ServicioReportes
from app.modules.reportes.infrastructure.repositorio_sql import RepositorioReportesSQL
from app.modules.stock.presentation.dependencias import obtener_servicio_stock


def obtener_servicio_reportes(uow: UoW) -> ServicioReportes:
    return ServicioReportes(RepositorioReportesSQL(uow), obtener_servicio_stock(uow))


ServicioReportesDep = Annotated[ServicioReportes, Depends(obtener_servicio_reportes)]
