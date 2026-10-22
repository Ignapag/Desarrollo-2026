"""Matrices por rol y autoridad vigente, independientes del transporte HTTP."""

from typing import Protocol

from app.errores import DatosInvalidos, NoAutenticado, NoEncontrado, ReglaDeNegocio, SinPermiso
from app.modules.usuarios.domain.entidades import ClaimsSesion, Rol
from app.modules.usuarios.domain.permisos import (
    ROLES,
    TODOS_LOS_PERMISOS,
    catalogo_modulos,
    permisos_disponibles,
)


class RepositorioAcceso(Protocol):
    async def identidad(self, usuario_id: int) -> dict | None: ...
    async def permisos(self, rol: str) -> list[str]: ...
    async def roles(self) -> list[dict]: ...
    async def guardar(
        self, rol: str, permisos: list[str], version: int, ejecutor_id: int | None,
    ) -> dict | None: ...


class ServicioAcceso:
    def __init__(self, repo: RepositorioAcceso):
        self.repo = repo

    async def sesion(self, token: ClaimsSesion) -> ClaimsSesion:
        usuario = await self.repo.identidad(token.usuario_id)
        if not usuario or usuario["estado"] != "ACTIVO":
            raise NoAutenticado("La cuenta no está activa. Volvé a iniciar sesión.")
        rol = Rol(usuario["rol"])
        permisos = (
            TODOS_LOS_PERMISOS if rol == Rol.ADMINISTRADOR
            else frozenset(await self.repo.permisos(rol.value))
        )
        return ClaimsSesion(usuario["id"], rol, usuario["username"], permisos)

    @staticmethod
    def _salida(fila: dict) -> dict:
        rol = fila["rol"]
        return {
            **fila, "nombre": ROLES[rol], "editable": rol not in {"ADMINISTRADOR", "CLIENTE"},
            "disponibles": sorted(permisos_disponibles(rol)),
            "permisos": sorted(TODOS_LOS_PERMISOS if rol == "ADMINISTRADOR" else fila["permisos"]),
        }

    async def consultar(self) -> dict:
        return {
            "modulos": catalogo_modulos(),
            "roles": [self._salida(fila) for fila in await self.repo.roles()],
        }

    async def guardar(
        self, rol: str, permisos: list[str], version: int, ejecutor_id: int | None,
    ) -> dict:
        if rol not in ROLES:
            raise NoEncontrado("El rol no existe")
        if rol in {"ADMINISTRADOR", "CLIENTE"}:
            raise SinPermiso("Este rol tiene permisos protegidos")
        valores = set(permisos)
        if valores - TODOS_LOS_PERMISOS:
            raise DatosInvalidos("Hay permisos desconocidos")
        if valores - permisos_disponibles(rol):
            raise SinPermiso("Estos permisos no son compatibles con el rol seleccionado")
        actualizado = await self.repo.guardar(rol, sorted(valores), version, ejecutor_id)
        if actualizado is None:
            raise ReglaDeNegocio(
                "Otro administrador cambió estos permisos. Actualizá y revisá de nuevo."
            )
        return self._salida(actualizado)
