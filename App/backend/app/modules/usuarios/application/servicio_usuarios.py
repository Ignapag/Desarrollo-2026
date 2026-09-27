"""Casos de uso de gestion de cuentas internas (CU_USR_02 a CU_USR_06).

Estan a cargo del Administrador. El login (CU_USR_01) es un caso de uso
aparte, con su propia autorizacion: vive en servicio_auth.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from app.core import auditoria
from app.core.db import UnidadDeTrabajo
from app.core.errores import NoEncontrado, ReglaDeNegocio
from app.core.seguridad import hashear_password
from app.modules.usuarios.domain.entidades import AccionesAuditoria, Rol, validar_password
from app.modules.usuarios.infrastructure.repositorio_sql import RepositorioUsuariosSQL

ROLES_VALIDOS = {rol.value for rol in Rol}
ESTADOS_VALIDOS = {"ACTIVO", "INACTIVO"}


@dataclass(slots=True, frozen=True)
class FiltrosUsuario:
    nombre: str | None = None
    apellido: str | None = None
    username: str | None = None
    rol: str | None = None
    estado: str | None = None


@dataclass(slots=True, frozen=True)
class DatosNuevoUsuario:
    nombre: str
    apellido: str
    username: str
    password: str
    rol: str
    email: str | None = None
    telefono: str | None = None


@dataclass(slots=True, frozen=True)
class DatosUsuario:
    """Campos editables por CU_USR_05. El rol se cambia con asignar_rol()."""

    nombre: str
    apellido: str
    username: str
    estado: str


class ServicioUsuarios:
    def __init__(self, uow: UnidadDeTrabajo, repositorio: RepositorioUsuariosSQL) -> None:
        self.uow = uow
        self.repo = repositorio

    # ------------------------------ CU_USR_02: buscar -------------------

    async def buscar(self, filtros: FiltrosUsuario) -> list[dict]:
        return await self.repo.buscar(
            nombre=filtros.nombre,
            apellido=filtros.apellido,
            username=filtros.username,
            rol=filtros.rol,
            estado=filtros.estado,
        )

    async def obtener(self, usuario_id: int) -> dict:
        usuario = await self.repo.por_id(usuario_id)
        if usuario is None:
            raise NoEncontrado("El usuario no existe")
        return usuario

    # ------------------------------ CU_USR_03: registrar -----------------

    async def registrar(self, datos: DatosNuevoUsuario, *, ejecutor_id: int | None) -> dict:
        if datos.rol not in ROLES_VALIDOS:
            raise ReglaDeNegocio(f"Rol invalido: {datos.rol}")
        validar_password(datos.password, username=datos.username)

        if await self.repo.existe_username(datos.username):
            raise ReglaDeNegocio("Ese nombre de usuario ya existe")

        password_hash = hashear_password(datos.password)
        try:
            usuario_id = await self.repo.crear(
                nombre=datos.nombre,
                apellido=datos.apellido,
                username=datos.username,
                email=datos.email,
                telefono=datos.telefono,
                password_hash=password_hash,
                rol=datos.rol,
            )
        except psycopg.errors.UniqueViolation as exc:
            # Carrera entre el chequeo de arriba y el INSERT: la restriccion
            # UNIQUE de la base es la que realmente lo garantiza.
            raise ReglaDeNegocio("Ese nombre de usuario ya existe") from exc

        await auditoria.registrar(
            self.uow,
            accion=AccionesAuditoria.USUARIO_REGISTRADO,
            entidad="usuario",
            entidad_id=usuario_id,
            usuario_id=ejecutor_id,
            datos={"username": datos.username, "rol": datos.rol},
        )
        return await self.obtener(usuario_id)

    # ------------------------------ CU_USR_04: desactivar -----------------

    async def desactivar(self, usuario_id: int, *, ejecutor_id: int | None) -> dict:
        usuario = await self.obtener(usuario_id)
        if usuario["estado"] == "INACTIVO":
            raise ReglaDeNegocio("El usuario ya esta inactivo")

        if await self.repo.tiene_actividad_operativa(usuario_id):
            raise ReglaDeNegocio(
                "El usuario tiene actividad operativa en curso (viajes abiertos); "
                "resolvela antes de desactivarlo"
            )

        await self.repo.cambiar_estado(usuario_id, "INACTIVO")
        await auditoria.registrar(
            self.uow,
            accion=AccionesAuditoria.USUARIO_DESACTIVADO,
            entidad="usuario",
            entidad_id=usuario_id,
            usuario_id=ejecutor_id,
        )
        return await self.obtener(usuario_id)

    # ------------------------------ CU_USR_05: modificar ------------------

    async def modificar(
        self, usuario_id: int, datos: DatosUsuario, *, ejecutor_id: int | None
    ) -> dict:
        actual = await self.obtener(usuario_id)
        if datos.estado not in ESTADOS_VALIDOS:
            raise ReglaDeNegocio(f"Estado invalido: {datos.estado}")
        if datos.username != actual["username"] and await self.repo.existe_username(
            datos.username, excluir_id=usuario_id
        ):
            raise ReglaDeNegocio("Ese nombre de usuario ya existe")

        await self.repo.actualizar(
            usuario_id,
            nombre=datos.nombre,
            apellido=datos.apellido,
            username=datos.username,
            estado=datos.estado,
        )
        await auditoria.registrar(
            self.uow,
            accion=AccionesAuditoria.USUARIO_MODIFICADO,
            entidad="usuario",
            entidad_id=usuario_id,
            usuario_id=ejecutor_id,
            datos={
                "nombre": datos.nombre,
                "apellido": datos.apellido,
                "username": datos.username,
                "estado": datos.estado,
            },
        )
        return await self.obtener(usuario_id)

    # ------------------------------ CU_USR_06: asignar rol ----------------

    async def asignar_rol(self, usuario_id: int, rol: str, *, ejecutor_id: int | None) -> dict:
        if rol not in ROLES_VALIDOS:
            raise ReglaDeNegocio(f"Rol invalido: {rol}")
        actual = await self.obtener(usuario_id)
        rol_anterior = actual["rol"]
        if rol_anterior == rol:
            return actual

        await self.repo.cambiar_rol(usuario_id, rol)
        await auditoria.registrar(
            self.uow,
            accion=AccionesAuditoria.ROL_ASIGNADO,
            entidad="usuario",
            entidad_id=usuario_id,
            usuario_id=ejecutor_id,
            datos={"rol_anterior": rol_anterior, "rol_nuevo": rol},
        )
        return await self.obtener(usuario_id)
