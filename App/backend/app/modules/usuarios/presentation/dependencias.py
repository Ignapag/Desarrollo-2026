"""Composicion, autenticacion y autorizacion del modulo de usuarios."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import settings
from app.core.dependencias import UoW
from app.core.seguridad import TokenInvalido, decodificar_token
from app.errores import NoAutenticado, SinPermiso
from app.modules.usuarios.application.servicio_acceso import ServicioAcceso
from app.modules.usuarios.application.servicio_auth import ServicioAuth
from app.modules.usuarios.application.servicio_usuarios import ServicioUsuarios
from app.modules.usuarios.domain.entidades import ROLES_PERSONAL_INTERNO, ClaimsSesion, Rol
from app.modules.usuarios.infrastructure.acceso_sql import RepositorioAccesoSQL
from app.modules.usuarios.infrastructure.repositorio_sql import RepositorioUsuariosSQL


def obtener_servicio_auth(uow: UoW) -> ServicioAuth:
    """Arma el servicio de inicio de sesión con el repositorio de usuarios."""
    return ServicioAuth(uow, RepositorioUsuariosSQL(uow))


ServicioAuthDep = Annotated[ServicioAuth, Depends(obtener_servicio_auth)]


def obtener_servicio_usuarios(uow: UoW) -> ServicioUsuarios:
    """Arma el servicio de gestión de cuentas con el repositorio de usuarios."""
    return ServicioUsuarios(uow, RepositorioUsuariosSQL(uow))


ServicioUsuariosDep = Annotated[ServicioUsuarios, Depends(obtener_servicio_usuarios)]


def usuario_actual(request: Request) -> ClaimsSesion:
    """Lee y valida el JWT de la cookie de sesión y devuelve su identidad.

    Lanza ``NoAutenticado`` si no hay cookie o el token es inválido o venció. Los permisos se cargan
    después desde la base.
    """
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


TokenSesion = Annotated[ClaimsSesion, Depends(usuario_actual)]


def obtener_servicio_acceso(uow: UoW) -> ServicioAcceso:
    """Arma el servicio de control de acceso con su repositorio SQL."""
    return ServicioAcceso(RepositorioAccesoSQL(uow))


ServicioAccesoDep = Annotated[ServicioAcceso, Depends(obtener_servicio_acceso)]


async def sesion_vigente(token: TokenSesion, acceso: ServicioAccesoDep, uow: UoW) -> ClaimsSesion:
    """Completa la identidad del token con el estado, rol y permisos vigentes en la base."""
    sesion = await acceso.sesion(token)
    await uow.atribuir_actor(sesion.usuario_id)
    return sesion


Sesion = Annotated[ClaimsSesion, Depends(sesion_vigente)]


def requiere_permiso(modulo: str, accion: str, *, cliente: bool = False):
    """Crea una dependencia que exige el permiso ``modulo.accion`` a la sesión.

    Con ``cliente=True`` los clientes también pasan; cada endpoint limita luego sus datos a los
    propios.
    """
    permiso = f"{modulo}.{accion}"

    def guardia(sesion: Sesion) -> ClaimsSesion:
        """Valida la sesión contra el permiso requerido y la devuelve."""
        if cliente and sesion.rol == Rol.CLIENTE:
            return sesion
        if sesion.rol == Rol.CLIENTE or not sesion.puede(permiso):
            raise SinPermiso("No tenés permiso para realizar esta operación")
        return sesion

    return guardia


def requiere_rol(*roles: Rol) -> Callable[[ClaimsSesion], ClaimsSesion]:
    """Crea una dependencia que solo admite los roles indicados."""
    permitidos = frozenset(roles)

    def guardia(claims: Sesion) -> ClaimsSesion:
        """Valida que el rol de la sesión esté entre los permitidos."""
        if claims.rol not in permitidos:
            raise SinPermiso(f"El rol {claims.rol.value} no tiene acceso a esta operacion")
        return claims

    return guardia


# Atajos de autorización por rol para usar en las firmas de los endpoints.
PersonalInterno = Annotated[ClaimsSesion, Depends(requiere_rol(*ROLES_PERSONAL_INTERNO))]
SoloAdministrador = Annotated[ClaimsSesion, Depends(requiere_rol(Rol.ADMINISTRADOR))]
SoloDuenio = Annotated[ClaimsSesion, Depends(requiere_rol(Rol.DUENIO))]
AdministradorODuenio = Annotated[
    ClaimsSesion, Depends(requiere_rol(Rol.ADMINISTRADOR, Rol.DUENIO))
]
SoloRepartidor = Annotated[ClaimsSesion, Depends(requiere_rol(Rol.REPARTIDOR))]
SoloCliente = Annotated[ClaimsSesion, Depends(requiere_rol(Rol.CLIENTE))]
