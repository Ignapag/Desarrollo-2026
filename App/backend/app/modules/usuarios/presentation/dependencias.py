"""Composicion, autenticacion y autorizacion del modulo de usuarios."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import settings
from app.core.dependencias import UoW
from app.core.errores import NoAutenticado, SinPermiso
from app.core.seguridad import TokenInvalido, decodificar_token
from app.modules.usuarios.application.servicio_auth import ServicioAuth
from app.modules.usuarios.application.servicio_usuarios import ServicioUsuarios
from app.modules.usuarios.domain.entidades import ROLES_PERSONAL_INTERNO, ClaimsSesion, Rol
from app.modules.usuarios.infrastructure.repositorio_sql import RepositorioUsuariosSQL


def obtener_servicio_auth(uow: UoW) -> ServicioAuth:
    return ServicioAuth(uow, RepositorioUsuariosSQL(uow))


ServicioAuthDep = Annotated[ServicioAuth, Depends(obtener_servicio_auth)]


def obtener_servicio_usuarios(uow: UoW) -> ServicioUsuarios:
    return ServicioUsuarios(uow, RepositorioUsuariosSQL(uow))


ServicioUsuariosDep = Annotated[ServicioUsuarios, Depends(obtener_servicio_usuarios)]


def usuario_actual(request: Request) -> ClaimsSesion:
    token = request.cookies.get(settings.cookie_sesion)
    if not token:
        raise NoAutenticado("No hay una sesion iniciada")
    try:
        payload = decodificar_token(token)
        return ClaimsSesion(
            usuario_id=int(payload["sub"]),
            rol=Rol(payload["rol"]),
            username=payload["username"],
        )
    except (TokenInvalido, KeyError, TypeError, ValueError) as exc:
        raise NoAutenticado("La sesion vencio o no es valida") from exc


Sesion = Annotated[ClaimsSesion, Depends(usuario_actual)]


def requiere_rol(*roles: Rol) -> Callable[[ClaimsSesion], ClaimsSesion]:
    permitidos = frozenset(roles)

    def guardia(claims: Sesion) -> ClaimsSesion:
        if claims.rol not in permitidos:
            raise SinPermiso(f"El rol {claims.rol.value} no tiene acceso a esta operacion")
        return claims

    return guardia


PersonalInterno = Annotated[ClaimsSesion, Depends(requiere_rol(*ROLES_PERSONAL_INTERNO))]
SoloAdministrador = Annotated[ClaimsSesion, Depends(requiere_rol(Rol.ADMINISTRADOR))]
SoloDuenio = Annotated[ClaimsSesion, Depends(requiere_rol(Rol.DUENIO))]
AdministradorODuenio = Annotated[
    ClaimsSesion, Depends(requiere_rol(Rol.ADMINISTRADOR, Rol.DUENIO))
]
SoloRepartidor = Annotated[ClaimsSesion, Depends(requiere_rol(Rol.REPARTIDOR))]
SoloCliente = Annotated[ClaimsSesion, Depends(requiere_rol(Rol.CLIENTE))]
