"""Composicion del modulo de notificaciones."""

from typing import Annotated

from fastapi import Depends

from app.core.dependencias import UoW
from app.modules.notificaciones.application.servicio_notificaciones import ServicioNotificaciones
from app.modules.notificaciones.infrastructure.enviadores import EnviadorSimulado
from app.modules.notificaciones.infrastructure.repositorio_sql import RepositorioNotificacionesSQL


def obtener_servicio_notificaciones(uow: UoW) -> ServicioNotificaciones:
    return ServicioNotificaciones(uow, RepositorioNotificacionesSQL(uow), EnviadorSimulado())


ServicioNotificacionesDep = Annotated[
    ServicioNotificaciones, Depends(obtener_servicio_notificaciones)
]
