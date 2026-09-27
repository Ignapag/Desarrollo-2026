"""Composicion del modulo de pagos y caja."""

from typing import Annotated

from fastapi import Depends

from app.core.dependencias import UoW
from app.modules.pagos.application.servicio_caja import ServicioCaja
from app.modules.pagos.application.servicio_conciliacion import ServicioConciliacion
from app.modules.pagos.application.servicio_pagos import ServicioPagos
from app.modules.pagos.infrastructure.repositorio_caja_sql import RepositorioCajaSQL
from app.modules.pagos.infrastructure.repositorio_sql import RepositorioPagosSQL


def obtener_servicio_pagos(uow: UoW) -> ServicioPagos:
    return ServicioPagos(uow, RepositorioPagosSQL(uow))


ServicioPagosDep = Annotated[ServicioPagos, Depends(obtener_servicio_pagos)]


def obtener_servicio_conciliacion(uow: UoW) -> ServicioConciliacion:
    return ServicioConciliacion(uow, RepositorioPagosSQL(uow))


ServicioConciliacionDep = Annotated[
    ServicioConciliacion, Depends(obtener_servicio_conciliacion)
]


def obtener_servicio_caja(uow: UoW) -> ServicioCaja:
    return ServicioCaja(uow, RepositorioCajaSQL(uow))


ServicioCajaDep = Annotated[ServicioCaja, Depends(obtener_servicio_caja)]
