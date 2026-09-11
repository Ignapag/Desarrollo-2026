"""Repositorio del modulo de delivery con SQL directo."""

from __future__ import annotations

from decimal import Decimal

from app.core.db import UnidadDeTrabajo
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
        valor = await self.uow.valor(
            "SELECT valor FROM parametro WHERE clave = %s", (clave,)
        )
        return valor if valor is not None else por_defecto

    # ------------------------------ consultas -------------------------

    async def pedidos_para_despachar(self) -> list[PedidoParaDespachar]:
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
            ORDER BY p.creado_en
            """
        )
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

    async def repartidores_disponibles(self) -> list[RepartidorDisponible]:
        """Repartidores disponibles y sin ningun viaje abierto."""
        filas = await self.uow.todos(
            """
            SELECT r.usuario_id, r.ultima_lat, r.ultima_lng,
                   u.nombre || ' ' || u.apellido AS nombre
            FROM repartidor r
            JOIN usuario u ON u.id = r.usuario_id
            WHERE r.estado = 'DISPONIBLE'
              AND u.estado = 'ACTIVO'
              AND NOT EXISTS (
                  SELECT 1 FROM viaje v
                  WHERE v.repartidor_id = r.usuario_id
                    AND v.estado IN ('PLANIFICADO','EN_RUTA')
              )
            ORDER BY r.usuario_id
            """
        )
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
            SELECT e.id, e.pedido_id, p.numero, e.estado, e.orden_en_viaje,
                   e.distancia_km, e.entregado_en,
                   d.calle, d.numero AS altura, d.piso_depto, d.referencia,
                   z.nombre AS zona_nombre,
                   c.telefono_whatsapp AS telefono_cliente,
                   u.nombre || ' ' || u.apellido AS cliente_nombre
            FROM envio e
            JOIN pedido p ON p.id = e.pedido_id
            LEFT JOIN direccion d ON d.id = p.direccion_id
            LEFT JOIN zona_cobertura z ON z.id = e.zona_id
            JOIN cliente c ON c.usuario_id = p.cliente_id
            JOIN usuario u ON u.id = c.usuario_id
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
            SELECT e.id, e.pedido_id, e.viaje_id, e.estado,
                   v.repartidor_id, v.estado AS estado_viaje
            FROM envio e
            LEFT JOIN viaje v ON v.id = e.viaje_id
            WHERE e.id = %s
            """,
            (envio_id,),
        )

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
        return fila["id"]  # type: ignore[index]

    async def cambiar_estado_repartidor(self, repartidor_id: int, estado: str) -> None:
        await self.uow.ejecutar(
            "UPDATE repartidor SET estado = %s WHERE usuario_id = %s",
            (estado, repartidor_id),
        )

    async def cambiar_estado_viaje(self, viaje_id: int, estado: str) -> None:
        campo = {
            "EN_RUTA": ", salida_en = now()",
            "FINALIZADO": ", retorno_en = now()",
        }.get(estado, "")
        await self.uow.ejecutar(
            f"UPDATE viaje SET estado = %s {campo} WHERE id = %s", (estado, viaje_id)
        )

    async def cambiar_estado_envios_del_viaje(self, viaje_id: int, estado: str) -> list[int]:
        campo = {
            "EN_CAMINO": ", en_camino_en = now()",
            "ENTREGADO": ", entregado_en = now()",
        }.get(estado, "")
        filas = await self.uow.todos(
            f"""
            UPDATE envio SET estado = %s {campo}
            WHERE viaje_id = %s AND estado <> 'ENTREGADO'
            RETURNING pedido_id
            """,
            (estado, viaje_id),
        )
        return [f["pedido_id"] for f in filas]

    async def cambiar_estado_envio(self, envio_id: int, estado: str) -> None:
        campo = {
            "EN_CAMINO": ", en_camino_en = now()",
            "ENTREGADO": ", entregado_en = now()",
        }.get(estado, "")
        await self.uow.ejecutar(
            f"UPDATE envio SET estado = %s {campo} WHERE id = %s", (estado, envio_id)
        )

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

    # ----------------------- estados del pedido -----------------------

    async def cambiar_estado_pedido(
        self, pedido_id: int, estado: str, *, usuario_id: int | None, observacion: str | None = None
    ) -> None:
        """Cambia el estado y deja el rastro en pedido_estado_historial.

        El alcance exige el timestamp de cada cambio y quien lo hizo; no
        alcanza con actualizar pedido.estado.
        """
        anterior = await self.uow.valor("SELECT estado FROM pedido WHERE id = %s", (pedido_id,))

        marca = {
            "ENTREGADO": ", entregado_en = now()",
        }.get(estado, "")
        await self.uow.ejecutar(
            f"UPDATE pedido SET estado = %s {marca} WHERE id = %s", (estado, pedido_id)
        )
        await self.uow.ejecutar(
            """
            INSERT INTO pedido_estado_historial
                (pedido_id, estado_anterior, estado_nuevo, usuario_id, observacion)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (pedido_id, anterior, estado, usuario_id, observacion),
        )
