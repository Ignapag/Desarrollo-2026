"""Repositorio del modulo de delivery con SQL directo."""

from __future__ import annotations

from decimal import Decimal

from app.core.db import UnidadDeTrabajo
from app.errores import ReglaDeNegocio
from app.modules.delivery.domain.entidades import (
    PedidoParaDespachar,
    RepartidorDisponible,
)


def _float(valor) -> float | None:
    return float(valor) if valor is not None else None


class RepositorioDeliverySQL:
    def __init__(self, uow: UnidadDeTrabajo) -> None:
        self.uow = uow

    # ------------------------------ parametros ------------------------

    async def parametro(self, clave: str, por_defecto: str) -> str:
        valor = await self.uow.valor("SELECT valor FROM parametro WHERE clave = %s", (clave,))
        return valor if valor is not None else por_defecto

    # ------------------------------ consultas -------------------------

    async def pedidos_para_despachar(
        self, *, bloquear: bool = False, pedido_ids: list[int] | None = None
    ) -> list[PedidoParaDespachar]:
        """Pedidos de delivery listos que todavia no estan en ningun viaje.

        La ubicacion sale de la direccion del pedido; si la direccion no tiene
        zona resuelta, se intenta deducir con punto_en_zona() sobre los
        poligonos de cobertura.
        """
        filas = await self.uow.todos(
            """
            SELECT p.id AS pedido_id, p.numero, p.creado_en,
                   d.lat, d.lng,
                   COALESCE(d.zona_id, z.id) AS zona_id,
                   COALESCE(zd.nombre, z.nombre) AS zona_nombre
            FROM pedido p
            JOIN direccion d ON d.id = p.direccion_id
            LEFT JOIN zona_cobertura zd ON zd.id = d.zona_id
            LEFT JOIN LATERAL (
                SELECT zc.id, zc.nombre
                FROM zona_cobertura zc
                WHERE zc.activa AND punto_en_zona(d.lat, d.lng, zc.poligono)
                LIMIT 1
            ) z ON d.zona_id IS NULL
            WHERE p.estado = 'LISTO'
              AND p.tipo_entrega = 'DELIVERY'
              AND NOT EXISTS (
                  SELECT 1 FROM envio e
                  WHERE e.pedido_id = p.id AND e.viaje_id IS NOT NULL
              )
            """
            + (" AND p.id = ANY(%s)" if pedido_ids is not None else "")
            + " ORDER BY p.id"
            + (" FOR UPDATE OF p SKIP LOCKED" if bloquear else ""),
            (pedido_ids,) if pedido_ids is not None else None,
        )
        if bloquear:
            # FOR UPDATE no renueva el snapshot de subconsultas sobre envio.
            # Con los pedidos bloqueados, una sentencia nueva ve las asignaciones
            # que confirmaron mientras comenzaba la lectura inicial.
            if not filas:
                return []
            return await self.pedidos_para_despachar(pedido_ids=[f["pedido_id"] for f in filas])
        return [
            PedidoParaDespachar(
                pedido_id=f["pedido_id"],
                numero=f["numero"],
                zona_id=f["zona_id"],
                zona_nombre=f["zona_nombre"],
                lat=_float(f["lat"]),
                lng=_float(f["lng"]),
                creado_en=f["creado_en"],
            )
            for f in filas
        ]

    async def repartidores_disponibles(
        self, *, bloquear: bool = False
    ) -> list[RepartidorDisponible]:
        """Repartidores disponibles y sin ningun viaje abierto."""
        filas = await self.uow.todos(
            """
            SELECT r.usuario_id, r.ultima_lat, r.ultima_lng,
                   u.nombre || ' ' || u.apellido AS nombre
            FROM repartidor r
            JOIN usuario u ON u.id = r.usuario_id
            WHERE r.estado = 'DISPONIBLE'
              AND u.estado = 'ACTIVO'
              AND u.rol = 'REPARTIDOR'
              AND NOT EXISTS (
                  SELECT 1 FROM viaje v
                  WHERE v.repartidor_id = r.usuario_id
                    AND v.estado IN ('PLANIFICADO','EN_RUTA')
              )
            ORDER BY r.usuario_id
            """
            + (" FOR UPDATE OF r SKIP LOCKED" if bloquear else "")
        )
        if bloquear:
            # El JOIN usuario puede provenir del snapshot anterior a esperar el perfil.
            # Gestion de cuentas toma el mismo lock antes de modificar estado o rol.
            ids_bloqueados = {fila["usuario_id"] for fila in filas}
            if not ids_bloqueados:
                return []
            return [
                repartidor
                for repartidor in await self.repartidores_disponibles()
                if repartidor.repartidor_id in ids_bloqueados
            ]
        return [
            RepartidorDisponible(
                repartidor_id=f["usuario_id"],
                nombre=f["nombre"],
                lat=_float(f["ultima_lat"]),
                lng=_float(f["ultima_lng"]),
            )
            for f in filas
        ]

    async def viaje(self, viaje_id: int) -> dict | None:
        return await self.uow.uno(
            """
            SELECT v.id, v.repartidor_id, v.estado, v.creado_en, v.salida_en,
                   v.retorno_en, u.nombre || ' ' || u.apellido AS repartidor_nombre
            FROM viaje v
            JOIN usuario u ON u.id = v.repartidor_id
            WHERE v.id = %s
            """,
            (viaje_id,),
        )

    async def envios_del_viaje(self, viaje_id: int) -> list[dict]:
        return await self.uow.todos(
            """
            SELECT e.id, e.id AS envio_id, e.viaje_id, e.pedido_id, p.numero,
                   p.total, GREATEST(p.total - COALESCE((
                       SELECT sum(CASE WHEN pg.tipo = 'COBRO' THEN pg.monto ELSE -pg.monto END)
                       FROM pago pg WHERE pg.pedido_id = p.id AND pg.estado = 'CONCILIADO'
                   ), 0), 0) AS saldo_pendiente,
                   e.estado, e.orden_en_viaje,
                   e.distancia_km, e.entregado_en,
                   d.calle, d.numero AS altura, d.piso_depto, d.referencia,
                   z.nombre AS zona_nombre,
                   c.telefono_whatsapp AS telefono_cliente,
                   COALESCE(NULLIF(concat_ws(' ', u.nombre, u.apellido), ''), c.nombre)
                       AS cliente_nombre
            FROM envio e
            JOIN pedido p ON p.id = e.pedido_id
            LEFT JOIN direccion d ON d.id = p.direccion_id
            LEFT JOIN zona_cobertura z ON z.id = e.zona_id
            JOIN cliente c ON c.id = p.cliente_id
            LEFT JOIN usuario u ON u.id = c.usuario_id
            WHERE e.viaje_id = %s
            ORDER BY e.orden_en_viaje
            """,
            (viaje_id,),
        )

    async def viajes_activos(self) -> list[dict]:
        return await self.uow.todos(
            """
            SELECT v.id, v.estado, v.creado_en, v.salida_en,
                   v.repartidor_id, u.nombre || ' ' || u.apellido AS repartidor_nombre,
                   count(e.id) AS cantidad_envios
            FROM viaje v
            JOIN usuario u ON u.id = v.repartidor_id
            LEFT JOIN envio e ON e.viaje_id = v.id
            WHERE v.estado IN ('PLANIFICADO','EN_RUTA')
            GROUP BY v.id, v.estado, v.creado_en, v.salida_en, v.repartidor_id, u.nombre, u.apellido
            ORDER BY v.creado_en
            """
        )

    async def viaje_abierto_de(self, repartidor_id: int) -> dict | None:
        return await self.uow.uno(
            """
            SELECT id, estado FROM viaje
            WHERE repartidor_id = %s AND estado IN ('PLANIFICADO','EN_RUTA')
            """,
            (repartidor_id,),
        )

    async def envio(self, envio_id: int) -> dict | None:
        return await self.uow.uno(
            """
            SELECT e.*, p.numero AS pedido_numero,
                   v.repartidor_id, v.estado AS estado_viaje, v.salida_en
            FROM envio e
            JOIN pedido p ON p.id = e.pedido_id
            LEFT JOIN viaje v ON v.id = e.viaje_id
            WHERE e.id = %s
            """,
            (envio_id,),
        )

    async def envio_del_pedido(self, pedido_id: int) -> dict | None:
        envio_id = await self.uow.valor("SELECT id FROM envio WHERE pedido_id = %s", (pedido_id,))
        return await self.envio(envio_id) if envio_id is not None else None

    # ------------------------------ escrituras ------------------------

    async def crear_viaje(
        self, repartidor_id: int, *, asignado_por: int | None, automatica: bool
    ) -> int:
        fila = await self.uow.uno(
            """
            INSERT INTO viaje (repartidor_id, asignado_por, asignacion_auto)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (repartidor_id, asignado_por, automatica),
        )
        return fila["id"]  # type: ignore[index]

    async def asignar_envio(
        self,
        *,
        pedido_id: int,
        viaje_id: int,
        zona_id: int | None,
        orden: int,
        distancia_km: float | None,
    ) -> int:
        """Crea el envio, o lo engancha al viaje si ya existia sin asignar."""
        fila = await self.uow.uno(
            """
            INSERT INTO envio (pedido_id, viaje_id, zona_id, orden_en_viaje,
                               estado, distancia_km, asignado_en)
            VALUES (%s, %s, %s, %s, 'ASIGNADO', %s, now())
            ON CONFLICT (pedido_id) DO UPDATE
               SET viaje_id = EXCLUDED.viaje_id,
                   zona_id = COALESCE(EXCLUDED.zona_id, envio.zona_id),
                   orden_en_viaje = EXCLUDED.orden_en_viaje,
                   estado = 'ASIGNADO',
                   distancia_km = EXCLUDED.distancia_km,
                   asignado_en = now()
            WHERE envio.viaje_id IS NULL
            RETURNING id
            """,
            (
                pedido_id,
                viaje_id,
                zona_id,
                orden,
                Decimal(str(distancia_km)) if distancia_km is not None else None,
            ),
        )
        if fila is None:
            raise ReglaDeNegocio("El pedido ya tiene una asignacion vigente")
        return fila["id"]

    async def cambiar_estado_repartidor(self, repartidor_id: int, estado: str) -> None:
        await self.uow.ejecutar(
            "UPDATE repartidor SET estado = %s WHERE usuario_id = %s",
            (estado, repartidor_id),
        )

    async def cambiar_estado_viaje(self, viaje_id: int, estado: str) -> None:
        if estado == "EN_RUTA":
            await self.uow.ejecutar(
                "UPDATE viaje SET estado = %s, salida_en = now() WHERE id = %s",
                (estado, viaje_id),
            )
            return
        if estado == "FINALIZADO":
            await self.uow.ejecutar(
                "UPDATE viaje SET estado = %s, retorno_en = now() WHERE id = %s",
                (estado, viaje_id),
            )
            return
        await self.uow.ejecutar("UPDATE viaje SET estado = %s WHERE id = %s", (estado, viaje_id))

    async def cambiar_estado_envios_del_viaje(self, viaje_id: int, estado: str) -> list[int]:
        if estado == "EN_CAMINO":
            sql = """
            UPDATE envio SET estado = %s, en_camino_en = now()
            WHERE viaje_id = %s AND estado <> 'ENTREGADO'
            RETURNING pedido_id
            """
        elif estado == "ENTREGADO":
            sql = """
            UPDATE envio SET estado = %s, entregado_en = now()
            WHERE viaje_id = %s AND estado <> 'ENTREGADO'
            RETURNING pedido_id
            """
        else:
            sql = """
            UPDATE envio SET estado = %s
            WHERE viaje_id = %s AND estado <> 'ENTREGADO'
            RETURNING pedido_id
            """
        filas = await self.uow.todos(sql, (estado, viaje_id))
        return [f["pedido_id"] for f in filas]

    async def cambiar_estado_envio(self, envio_id: int, estado: str) -> None:
        if estado == "EN_CAMINO":
            sql = "UPDATE envio SET estado = %s, en_camino_en = now() WHERE id = %s"
        elif estado == "ENTREGADO":
            sql = "UPDATE envio SET estado = %s, entregado_en = now() WHERE id = %s"
        else:
            sql = "UPDATE envio SET estado = %s WHERE id = %s"
        await self.uow.ejecutar(sql, (estado, envio_id))

    async def quedan_envios_pendientes(self, viaje_id: int) -> bool:
        return bool(
            await self.uow.valor(
                """
                SELECT EXISTS (
                    SELECT 1 FROM envio
                    WHERE viaje_id = %s AND estado NOT IN ('ENTREGADO','FALLIDO')
                )
                """,
                (viaje_id,),
            )
        )

    async def bloquear_viaje(self, viaje_id: int) -> dict | None:
        # Todos los comandos usan pedido(s) -> viaje -> envio -> repartidor.
        await self.uow.todos(
            """SELECT p.id FROM pedido p JOIN envio e ON e.pedido_id = p.id
               WHERE e.viaje_id = %s ORDER BY p.id FOR UPDATE OF p""",
            (viaje_id,),
        )
        await self.uow.valor("SELECT id FROM viaje WHERE id = %s FOR UPDATE", (viaje_id,))
        return await self.viaje(viaje_id)

    async def pedido_asignable(self, pedido_id: int) -> dict | None:
        return await self.uow.uno(
            """SELECT p.id, p.estado, p.tipo_entrega, d.zona_id
               FROM pedido p LEFT JOIN direccion d ON d.id = p.direccion_id
               WHERE p.id = %s FOR UPDATE OF p""",
            (pedido_id,),
        )

    async def desenganchar_envio(self, envio_id: int, motivo: str) -> None:
        await self.uow.ejecutar(
            """UPDATE envio SET viaje_id = NULL, estado = 'PENDIENTE',
               asignado_en = NULL, en_camino_en = NULL, entregado_en = NULL,
               observaciones = %s WHERE id = %s""",
            (motivo, envio_id),
        )

    async def registrar_fallo(self, envio_id: int, motivo: str) -> None:
        await self.uow.ejecutar(
            "UPDATE envio SET estado = 'FALLIDO', observaciones = %s WHERE id = %s",
            (motivo, envio_id),
        )
