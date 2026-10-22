"""Persistencia transaccional de permisos y control de versiones por rol."""

from app.core import auditoria
from app.core.db import UnidadDeTrabajo


class RepositorioAccesoSQL:
    def __init__(self, uow: UnidadDeTrabajo):
        self.uow = uow

    async def identidad(self, usuario_id: int) -> dict | None:
        return await self.uow.uno(
            "SELECT id, rol, username, estado FROM usuario WHERE id=%s", (usuario_id,),
        )

    async def permisos(self, rol: str) -> list[str]:
        filas = await self.uow.todos(
            "SELECT permiso FROM rol_permiso WHERE rol=%s ORDER BY permiso", (rol,),
        )
        return [fila["permiso"] for fila in filas]

    async def roles(self) -> list[dict]:
        return await self.uow.todos(
            """SELECT r.rol, r.version,
                      COALESCE(array_agg(p.permiso ORDER BY p.permiso)
                          FILTER (WHERE p.permiso IS NOT NULL), ARRAY[]::text[]) AS permisos
               FROM rol_acceso r LEFT JOIN rol_permiso p ON p.rol=r.rol
               GROUP BY r.rol, r.version ORDER BY r.rol"""
        )

    async def guardar(self, rol, permisos, version, ejecutor_id):
        anterior = await self.uow.uno(
            "SELECT version FROM rol_acceso WHERE rol=%s FOR UPDATE", (rol,),
        )
        if anterior is None or anterior["version"] != version:
            return None
        previos = await self.permisos(rol)
        await self.uow.ejecutar("DELETE FROM rol_permiso WHERE rol=%s", (rol,))
        for permiso in permisos:
            await self.uow.ejecutar(
                "INSERT INTO rol_permiso (rol, permiso) VALUES (%s,%s)", (rol, permiso),
            )
        await self.uow.ejecutar(
            "UPDATE rol_acceso SET version=version+1 WHERE rol=%s", (rol,),
        )
        await auditoria.registrar(
            self.uow, accion="PERMISOS_MODIFICADOS", entidad="rol", entidad_id=rol,
            usuario_id=ejecutor_id,
            datos={"anteriores": previos, "nuevos": permisos, "version": version + 1},
        )
        return {"rol": rol, "permisos": permisos, "version": version + 1}
