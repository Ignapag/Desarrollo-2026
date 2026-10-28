"""Caso de uso de autenticacion (CU_USR_01: Iniciar sesion).

La capa de presentacion nunca importa bcrypt ni PyJWT: solo pide
`iniciar_sesion(...)` y recibe un token listo para poner en la cookie.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core import auditoria
from app.core.db import UnidadDeTrabajo
from app.core.seguridad import crear_token, verificar_password
from app.errores import NoAutenticado
from app.modules.usuarios.domain.entidades import AccionesAuditoria, Rol
from app.modules.usuarios.infrastructure.repositorio_sql import RepositorioUsuariosSQL

MENSAJE_CREDENCIALES_INVALIDAS = "Usuario o contrasenia incorrectos"
MENSAJE_CUENTA_INACTIVA = "La cuenta esta inactiva; contacta a un administrador"


@dataclass(slots=True, frozen=True)
class SesionIniciada:
    """Resultado de un inicio de sesión exitoso: token y datos del usuario."""

    token: str
    usuario_id: int
    nombre: str
    apellido: str
    username: str
    rol: Rol


class ServicioAuth:
    """Caso de uso de inicio de sesión con auditoría de intentos."""

    def __init__(self, uow: UnidadDeTrabajo, repositorio: RepositorioUsuariosSQL) -> None:
        """Recibe la unidad de trabajo y el repositorio de usuarios."""
        self.uow = uow
        self.repo = repositorio

    async def iniciar_sesion(
        self, *, username: str, password: str, ip: str | None = None
    ) -> SesionIniciada:
        """Valida credenciales y devuelve un token de sesion.

        El mensaje de error nunca distingue "el usuario no existe" de "la
        contrasenia es incorrecta": decirlo facilitaria enumerar nombres de
        usuario validos por fuerza bruta.
        """
        fila = await self.repo.por_username(username)
        # Credenciales inválidas: se audita el intento fallido sin revelar la causa.
        if fila is None or not verificar_password(password, fila["password_hash"]):
            await auditoria.registrar(
                self.uow,
                accion=AccionesAuditoria.SESION_FALLIDA,
                entidad="usuario",
                entidad_id=fila["id"] if fila else None,
                datos={"username": username},
                ip=ip,
            )
            raise NoAutenticado(MENSAJE_CREDENCIALES_INVALIDAS)

        if fila["estado"] != "ACTIVO":
            raise NoAutenticado(MENSAJE_CUENTA_INACTIVA)

        # Inicio exitoso: se registra el acceso y se emite el token.
        await self.repo.actualizar_ultimo_acceso(fila["id"])
        await auditoria.registrar(
            self.uow,
            accion=AccionesAuditoria.SESION_INICIADA,
            entidad="usuario",
            entidad_id=fila["id"],
            usuario_id=fila["id"],
            ip=ip,
        )

        token = crear_token(usuario_id=fila["id"], rol=fila["rol"], username=fila["username"])
        return SesionIniciada(
            token=token,
            usuario_id=fila["id"],
            nombre=fila["nombre"],
            apellido=fila["apellido"],
            username=fila["username"],
            rol=Rol(fila["rol"]),
        )
