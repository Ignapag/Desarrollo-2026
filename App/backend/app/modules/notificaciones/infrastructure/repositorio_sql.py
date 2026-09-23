"""Repositorio del modulo de Notificaciones, con SQL directo."""

from __future__ import annotations

from app.core.db import UnidadDeTrabajo
from app.modules.notificaciones.domain.entidades import NotificacionPendiente, PlantillaActiva


class RepositorioNotificacionesSQL:
    def __init__(self, uow: UnidadDeTrabajo) -> None:
        self.uow = uow

    # ------------------------------ plantillas (CU_BOT_04 a 07) ----------

    async def plantilla_activa(self, clave: str) -> PlantillaActiva | None:
        fila = await self.uow.uno(
            """
            SELECT id, clave, nombre, cuerpo FROM notificacion_plantilla
            WHERE clave = %s AND activa
            ORDER BY actualizado_en DESC
            LIMIT 1
            """,
            (clave,),
        )
        return PlantillaActiva(**fila) if fila else None

    async def buscar_plantillas(
        self, *, nombre: str | None, evento: str | None, activa: bool | None
    ) -> list[dict]:
        condiciones: list[str] = []
        parametros: list[object] = []
        if nombre:
            condiciones.append("nombre ILIKE %s")
            parametros.append(f"%{nombre}%")
        if evento:
            condiciones.append("clave = %s")
            parametros.append(evento)
        if activa is not None:
            condiciones.append("activa = %s")
            parametros.append(activa)
        where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
        return await self.uow.todos(
            f"""
            SELECT id, clave, nombre, cuerpo, activa, actualizado_por, actualizado_en
            FROM notificacion_plantilla {where}
            ORDER BY clave, actualizado_en DESC
            """,
            parametros,
        )

    async def obtener_plantilla(self, plantilla_id: int) -> dict | None:
        return await self.uow.uno(
            """
            SELECT id, clave, nombre, cuerpo, activa, actualizado_por, actualizado_en
            FROM notificacion_plantilla WHERE id = %s
            """,
            (plantilla_id,),
        )

    async def crear_plantilla(
        self, *, clave: str, nombre: str, cuerpo: str, activa: bool, actualizado_por: int | None
    ) -> int:
        fila = await self.uow.uno(
            """
            INSERT INTO notificacion_plantilla (clave, nombre, cuerpo, activa, actualizado_por)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (clave, nombre, cuerpo, activa, actualizado_por),
        )
        return fila["id"]  # type: ignore[index]

    async def actualizar_plantilla(
        self,
        plantilla_id: int,
        *,
        nombre: str,
        cuerpo: str,
        activa: bool,
        actualizado_por: int | None,
    ) -> None:
        await self.uow.ejecutar(
            """
            UPDATE notificacion_plantilla
               SET nombre = %s, cuerpo = %s, activa = %s,
                   actualizado_por = %s, actualizado_en = now()
             WHERE id = %s
            """,
            (nombre, cuerpo, activa, actualizado_por, plantilla_id),
        )

    async def cambiar_estado_plantilla(
        self, plantilla_id: int, *, activa: bool, actualizado_por: int | None
    ) -> None:
        await self.uow.ejecutar(
            """
            UPDATE notificacion_plantilla
               SET activa = %s, actualizado_por = %s, actualizado_en = now()
             WHERE id = %s
            """,
            (activa, actualizado_por, plantilla_id),
        )

    # ------------------------------ notificaciones ------------------------

    async def crear(
        self,
        *,
        plantilla_id: int,
        clave: str,
        destinatario: str,
        cliente_id: int | None,
        pedido_id: int | None,
        cuerpo_renderizado: str,
    ) -> int:
        fila = await self.uow.uno(
            """
            INSERT INTO notificacion
                (plantilla_id, clave, destinatario, cliente_id, pedido_id, cuerpo_renderizado)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (plantilla_id, clave, destinatario, cliente_id, pedido_id, cuerpo_renderizado),
        )
        return fila["id"]  # type: ignore[index]

    async def pendientes(self, *, limite: int) -> list[NotificacionPendiente]:
        filas = await self.uow.todos(
            """
            SELECT id, destinatario, cuerpo_renderizado, intentos
            FROM notificacion
            WHERE estado = 'PENDIENTE'
            ORDER BY creada_en
            LIMIT %s
            """,
            (limite,),
        )
        return [NotificacionPendiente(**f) for f in filas]

    async def marcar_enviada(self, notificacion_id: int) -> None:
        await self.uow.ejecutar(
            """
            UPDATE notificacion
               SET estado = 'ENVIADA', enviada_en = now(), intentos = intentos + 1
             WHERE id = %s
            """,
            (notificacion_id,),
        )

    async def marcar_fallida(self, notificacion_id: int, *, error: str) -> None:
        await self.uow.ejecutar(
            """
            UPDATE notificacion
               SET estado = 'FALLIDA', error = %s, intentos = intentos + 1
             WHERE id = %s
            """,
            (error, notificacion_id),
        )

    async def listar(
        self, *, pedido_id: int | None, estado: str | None, limite: int
    ) -> list[dict]:
        condiciones: list[str] = []
        parametros: list[object] = []
        if pedido_id is not None:
            condiciones.append("pedido_id = %s")
            parametros.append(pedido_id)
        if estado is not None:
            condiciones.append("estado = %s")
            parametros.append(estado)
        where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
        parametros.append(limite)
        return await self.uow.todos(
            f"""
            SELECT id, clave, destinatario, cliente_id, pedido_id, estado,
                   intentos, error, creada_en, enviada_en
            FROM notificacion {where}
            ORDER BY creada_en DESC
            LIMIT %s
            """,
            parametros,
        )
