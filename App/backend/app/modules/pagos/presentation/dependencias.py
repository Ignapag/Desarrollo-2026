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
    """Arma el servicio de registro de pagos con su repositorio SQL."""
    return ServicioPagos(uow, RepositorioPagosSQL(uow))


ServicioPagosDep = Annotated[ServicioPagos, Depends(obtener_servicio_pagos)]


def obtener_servicio_conciliacion(uow: UoW) -> ServicioConciliacion:
    """Arma el servicio de conciliación, que también usa el servicio de caja."""
    return ServicioConciliacion(uow, RepositorioPagosSQL(uow), obtener_servicio_caja(uow))


ServicioConciliacionDep = Annotated[
    ServicioConciliacion, Depends(obtener_servicio_conciliacion)
]


def obtener_servicio_caja(uow: UoW) -> ServicioCaja:
    """Arma el servicio de consolidación por turno y cierres de caja."""
    return ServicioCaja(uow, RepositorioCajaSQL(uow))


ServicioCajaDep = Annotated[ServicioCaja, Depends(obtener_servicio_caja)]
