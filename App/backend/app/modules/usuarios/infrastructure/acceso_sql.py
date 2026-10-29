"""Persistencia transaccional de permisos y control de versiones por rol."""

from app.core import auditoria
from app.core.db import UnidadDeTrabajo


class RepositorioAccesoSQL:
    """Acceso SQL a la matriz de permisos por rol y a la identidad de los usuarios."""

    def __init__(self, uow: UnidadDeTrabajo):
        """Recibe la unidad de trabajo cuya transacción comparten las consultas."""
        self.uow = uow

    async def identidad(self, usuario_id: int) -> dict | None:
        """Devuelve id, rol, username y estado del usuario, o ``None``."""
        return await self.uow.uno(
            "SELECT id, rol, username, estado FROM usuario WHERE id=%s", (usuario_id,),
        )

    async def permisos(self, rol: str) -> list[str]:
        """Devuelve los permisos concedidos a un rol, ordenados."""
        filas = await self.uow.todos(
            "SELECT permiso FROM rol_permiso WHERE rol=%s AND eliminado_en IS NULL "
            "ORDER BY permiso", (rol,),
        )
        return [fila["permiso"] for fila in filas]

    async def roles(self) -> list[dict]:
        """Devuelve cada rol con su versión y la lista de permisos concedidos."""
        return await self.uow.todos(
            """SELECT r.rol, r.version,
                      COALESCE(array_agg(p.permiso ORDER BY p.permiso)
                          FILTER (WHERE p.permiso IS NOT NULL), ARRAY[]::text[]) AS permisos
               FROM rol_acceso r LEFT JOIN rol_permiso p ON p.rol=r.rol AND p.eliminado_en IS NULL
               GROUP BY r.rol, r.version ORDER BY r.rol"""
        )

    async def guardar(self, rol, permisos, version, ejecutor_id):
        """Reemplaza los permisos del rol si la versión coincide, y lo audita.

        Devuelve ``None`` si otro administrador cambió el rol mientras tanto.
        """
        # Bloquea el rol y verifica la versión (concurrencia optimista).
        anterior = await self.uow.uno(
            "SELECT version FROM rol_acceso WHERE rol=%s FOR UPDATE", (rol,),
        )
        if anterior is None or anterior["version"] != version:
            return None
        previos = await self.permisos(rol)
        # Conserva concesiones revocadas; ninguna lectura de acceso las considera vigentes.
        await self.uow.ejecutar(
            "UPDATE rol_permiso SET eliminado_en=now() WHERE rol=%s "
            "AND eliminado_en IS NULL AND NOT (permiso=ANY(%s::text[]))", (rol, permisos),
        )
        for permiso in permisos:
            await self.uow.ejecutar(
                "INSERT INTO rol_permiso (rol, permiso) VALUES (%s,%s) "
                "ON CONFLICT (rol, permiso) DO UPDATE SET eliminado_en=NULL "
                "WHERE rol_permiso.eliminado_en IS NOT NULL", (rol, permiso),
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
