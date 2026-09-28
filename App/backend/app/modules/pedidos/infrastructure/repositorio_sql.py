"""Repositorio SQL parametrizado de pedidos."""

from decimal import Decimal

from app.core.db import UnidadDeTrabajo
from app.modules.pedidos.domain.entidades import EstadoPedido


class RepositorioPedidosSQL:
    def __init__(self, uow: UnidadDeTrabajo) -> None:
        self.uow = uow

    async def cliente_valido(self, cliente_id: int) -> bool:
        return bool(
            await self.uow.valor(
                """
                SELECT EXISTS (
                    SELECT 1 FROM cliente c
                    JOIN usuario u ON u.id = c.usuario_id
                    WHERE c.usuario_id = %s AND u.estado = 'ACTIVO'
                )
                """,
                (cliente_id,),
            )
        )

    async def direccion_valida(self, cliente_id: int, direccion_id: int) -> bool:
        return bool(
            await self.uow.valor(
                """
                SELECT EXISTS (
                    SELECT 1 FROM direccion
                    WHERE id = %s AND cliente_id = %s AND activa
                )
                """,
                (direccion_id, cliente_id),
            )
        )

    async def crear_direccion(self, cliente_id: int, datos: dict) -> int | None:
        zona_id = await self.uow.valor(
            "SELECT id FROM zona_cobertura WHERE lower(nombre) = lower(%s) AND activa",
            (datos["localidad"],),
        )
        if zona_id is None:
            return None
        fila = await self.uow.uno(
            """
            INSERT INTO direccion
                (cliente_id, calle, numero, localidad, referencia, zona_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                cliente_id,
                datos["calle"],
                datos["numero"],
                datos["localidad"],
                datos.get("referencia"),
                zona_id,
            ),
        )
        return fila["id"]

    async def productos(self, ids: list[int]) -> list[dict]:
        return await self.uow.todos(
            """
            SELECT p.id, p.nombre, p.precio_base, p.variantes,
                   p.activo AND pd.disponible AS disponible
            FROM producto p
            JOIN producto_disponible pd ON pd.producto_id = p.id
            WHERE p.id = ANY(%s)
            FOR SHARE OF p
            """,
            (ids,),
        )

    async def crear(
        self,
        *,
        cliente_id: int,
        tipo_entrega: str,
        direccion_id: int | None,
        observaciones: str | None,
        items: list[dict],
    ) -> dict:
        subtotal = sum(
            (Decimal(str(item["precio_unitario"])) * item["cantidad"] for item in items),
            Decimal("0"),
        )
        fila = await self.uow.uno(
            """
            INSERT INTO pedido
                (cliente_id, tipo_entrega, direccion_id, canal, estado,
                 subtotal, costo_envio, descuento_total, total, observaciones)
            VALUES (%s, %s, %s, 'WEB', 'PENDIENTE', %s, 0, 0, %s, %s)
            RETURNING id
            """,
            (cliente_id, tipo_entrega, direccion_id, subtotal, subtotal, observaciones),
        )
        pedido_id = fila["id"]
        for item in items:
            item_subtotal = Decimal(str(item["precio_unitario"])) * item["cantidad"]
            await self.uow.ejecutar(
                """
                INSERT INTO pedido_item
                    (pedido_id, producto_id, nombre_producto, cantidad,
                     precio_unitario, costo_opciones, subtotal, aclaraciones)
                VALUES (%s, %s, %s, %s, %s, 0, %s, %s)
                """,
                (
                    pedido_id,
                    item["producto_id"],
                    item["nombre_producto"],
                    item["cantidad"],
                    item["precio_unitario"],
                    item_subtotal,
                    item["aclaraciones"],
                ),
            )
        await self.uow.ejecutar(
            """
            INSERT INTO pedido_estado_historial (pedido_id, estado_nuevo, observacion)
            VALUES (%s, 'PENDIENTE', 'Pedido creado')
            """,
            (pedido_id,),
        )
        return await self.detalle(pedido_id)

    async def listar(self, *, cliente_id: int | None) -> list[dict]:
        pedidos = await self.uow.todos(
            """
            SELECT p.id, p.numero, p.cliente_id,
                   u.nombre || ' ' || u.apellido AS cliente,
                   p.tipo_entrega, p.direccion_id, p.estado, p.subtotal,
                   p.costo_envio, p.total, p.observaciones, p.creado_en
            FROM pedido p
            JOIN usuario u ON u.id = p.cliente_id
            WHERE (%s::bigint IS NULL OR p.cliente_id = %s)
            ORDER BY p.creado_en DESC, p.id DESC
            LIMIT 200
            """,
            (cliente_id, cliente_id),
        )
        for pedido in pedidos:
            pedido["items"] = await self._items(pedido["id"])
        return pedidos

    async def detalle(self, pedido_id: int) -> dict:
        pedido = await self.uow.uno(
            """
            SELECT p.id, p.numero, p.cliente_id,
                   u.nombre || ' ' || u.apellido AS cliente,
                   p.tipo_entrega, p.direccion_id, p.estado, p.subtotal,
                   p.costo_envio, p.total, p.observaciones, p.creado_en
            FROM pedido p
            JOIN usuario u ON u.id = p.cliente_id
            WHERE p.id = %s
            """,
            (pedido_id,),
        )
        pedido["items"] = await self._items(pedido_id)
        return pedido

    async def _items(self, pedido_id: int) -> list[dict]:
        return await self.uow.todos(
            """
            SELECT id, producto_id, nombre_producto, cantidad, precio_unitario,
                   costo_opciones, subtotal, aclaraciones
            FROM pedido_item WHERE pedido_id = %s ORDER BY id
            """,
            (pedido_id,),
        )

    async def obtener(self, pedido_id: int, *, bloquear: bool = False) -> dict | None:
        if bloquear:
            return await self.uow.uno(
                "SELECT id, estado FROM pedido WHERE id = %s FOR UPDATE", (pedido_id,)
            )
        return await self.uow.uno(
            "SELECT id, estado FROM pedido WHERE id = %s", (pedido_id,)
        )

    async def items_para_stock(self, pedido_id: int) -> list[dict]:
        return await self.uow.todos(
            "SELECT producto_id, cantidad FROM pedido_item WHERE pedido_id = %s",
            (pedido_id,),
        )

    async def cambiar_estado(
        self, pedido_id: int, estado: EstadoPedido, usuario_id: int | None
    ) -> dict:
        anterior = await self.uow.valor(
            "SELECT estado FROM pedido WHERE id = %s", (pedido_id,)
        )
        if estado == EstadoPedido.CONFIRMADO:
            sql = "UPDATE pedido SET estado = %s, confirmado_en = now() WHERE id = %s"
        elif estado == EstadoPedido.ENTREGADO:
            sql = "UPDATE pedido SET estado = %s, entregado_en = now() WHERE id = %s"
        elif estado == EstadoPedido.CANCELADO:
            sql = "UPDATE pedido SET estado = %s, cancelado_en = now() WHERE id = %s"
        else:
            sql = "UPDATE pedido SET estado = %s WHERE id = %s"
        await self.uow.ejecutar(sql, (estado.value, pedido_id))
        await self.uow.ejecutar(
            """
            INSERT INTO pedido_estado_historial
                (pedido_id, estado_anterior, estado_nuevo, usuario_id, observacion)
            VALUES (%s, %s, %s, %s, 'Cambio manual de estado')
            """,
            (pedido_id, anterior, estado.value, usuario_id),
        )
        return await self.detalle(pedido_id)
