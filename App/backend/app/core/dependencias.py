"""Dependencias de FastAPI compartidas por los modulos."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import settings
from app.core.db import UnidadDeTrabajo, conexion
from app.core.errores import NoAutenticado, SinPermiso
from app.core.seguridad import TokenInvalido, decodificar_token
from app.modules.delivery.application.servicio_delivery import ServicioDelivery
from app.modules.delivery.infrastructure.repositorio_sql import RepositorioDeliverySQL
from app.modules.notificaciones.application.servicio_notificaciones import ServicioNotificaciones
from app.modules.notificaciones.infrastructure.enviadores import EnviadorSimulado
from app.modules.notificaciones.infrastructure.repositorio_sql import RepositorioNotificacionesSQL
from app.modules.usuarios.application.servicio_auth import ServicioAuth
from app.modules.usuarios.application.servicio_usuarios import ServicioUsuarios
from app.modules.usuarios.domain.entidades import ROLES_PERSONAL_INTERNO, ClaimsSesion, Rol
from app.modules.usuarios.infrastructure.repositorio_sql import RepositorioUsuariosSQL


async def obtener_uow() -> AsyncIterator[UnidadDeTrabajo]:
    """Una transaccion por request: commit al terminar, rollback si hay error."""
    async with conexion() as conn:
        yield UnidadDeTrabajo(conn)


UoW = Annotated[UnidadDeTrabajo, Depends(obtener_uow)]


def obtener_servicio_delivery(uow: UoW) -> ServicioDelivery:
    return ServicioDelivery(uow, RepositorioDeliverySQL(uow))


ServicioDeliveryDep = Annotated[ServicioDelivery, Depends(obtener_servicio_delivery)]


def obtener_servicio_auth(uow: UoW) -> ServicioAuth:
    return ServicioAuth(uow, RepositorioUsuariosSQL(uow))


ServicioAuthDep = Annotated[ServicioAuth, Depends(obtener_servicio_auth)]


def obtener_servicio_usuarios(uow: UoW) -> ServicioUsuarios:
    return ServicioUsuarios(uow, RepositorioUsuariosSQL(uow))


ServicioUsuariosDep = Annotated[ServicioUsuarios, Depends(obtener_servicio_usuarios)]


def obtener_servicio_notificaciones(uow: UoW) -> ServicioNotificaciones:
    # EnviadorSimulado: adaptador de desarrollo. Cuando se integre WhatsApp
    # Cloud API / n8n, el enviador real se conecta aca (ver
    # app/modules/notificaciones/infrastructure/enviadores.py) y no cambia
    # nada mas en el modulo.
    return ServicioNotificaciones(uow, RepositorioNotificacionesSQL(uow), EnviadorSimulado())


ServicioNotificacionesDep = Annotated[
    ServicioNotificaciones, Depends(obtener_servicio_notificaciones)
]


def ip_cliente(request: Request) -> str | None:
    reenviado = request.headers.get("x-forwarded-for")
    if reenviado:
        return reenviado.split(",")[0].strip()
    return request.client.host if request.client else None


IpCliente = Annotated[str | None, Depends(ip_cliente)]


# ---------------------------------------------------------------------
# Autenticacion y autorizacion (EDT 1.8 - Usuarios y Seguridad).
#
# El guard SOLO decodifica el JWT de la cookie de sesion: no consulta la
# base. Por eso se declara antes que UoW/el servicio en la firma de
# cualquier endpoint protegido (ver docs/GUIA_EQUIPO.md, seccion 7): un
# pedido sin sesion valida se rechaza sin gastar una conexion.
#
#     empleado: PersonalInterno,   # <- la guarda va primero
#     servicio: ServicioDeliveryDep,
# ---------------------------------------------------------------------


def usuario_actual(request: Request) -> ClaimsSesion:
    token = request.cookies.get(settings.cookie_sesion)
    if not token:
        raise NoAutenticado("No hay una sesion iniciada")
    try:
        payload = decodificar_token(token)
    except TokenInvalido as exc:
        raise NoAutenticado("La sesion vencio o no es valida") from exc
    return ClaimsSesion(
        usuario_id=int(payload["sub"]),
        rol=Rol(payload["rol"]),
        username=payload["username"],
    )


Sesion = Annotated[ClaimsSesion, Depends(usuario_actual)]


def requiere_rol(*roles: Rol) -> Callable[[ClaimsSesion], ClaimsSesion]:
    """Fabrica una dependencia que exige uno de los roles dados.

    Uso puntual: `Annotated[ClaimsSesion, Depends(requiere_rol(Rol.EMPLEADO))]`.
    Para los casos comunes ya estan armados los alias de abajo
    (PersonalInterno, SoloAdministrador, etc.): preferilos antes de escribir
    una combinacion nueva.
    """
    permitidos = frozenset(roles)

    def guardia(claims: Sesion) -> ClaimsSesion:
        if claims.rol not in permitidos:
            raise SinPermiso(f"El rol {claims.rol.value} no tiene acceso a esta operacion")
        return claims

    return guardia


#: Cualquier rol que opere el panel interno (todos menos el Cliente). Es el
#: guard que Delivery y otros modulos ya esperan encontrar aca.
PersonalInterno = Annotated[ClaimsSesion, Depends(requiere_rol(*ROLES_PERSONAL_INTERNO))]

SoloAdministrador = Annotated[ClaimsSesion, Depends(requiere_rol(Rol.ADMINISTRADOR))]
AdministradorODuenio = Annotated[
    ClaimsSesion, Depends(requiere_rol(Rol.ADMINISTRADOR, Rol.DUENIO))
]
SoloRepartidor = Annotated[ClaimsSesion, Depends(requiere_rol(Rol.REPARTIDOR))]
SoloCliente = Annotated[ClaimsSesion, Depends(requiere_rol(Rol.CLIENTE))]
