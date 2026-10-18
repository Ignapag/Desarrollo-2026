"""Repositorio SQL parametrizado de pedidos."""

import json
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
                    LEFT JOIN usuario u ON u.id = c.usuario_id
                    WHERE c.id = %s AND c.estado = 'ACTIVO'
                      AND (c.usuario_id IS NULL OR u.estado = 'ACTIVO')
                )
                """,
                (cliente_id,),
            )
        )

    async def cliente_para_usuario(self, usuario_id: int) -> int | None:
        return await self.uow.valor(
            """
            SELECT c.id FROM cliente c JOIN usuario u ON u.id = c.usuario_id
            WHERE c.usuario_id = %s AND c.estado = 'ACTIVO' AND u.estado = 'ACTIVO'
            """,
            (usuario_id,),
        )

    async def direccion_valida(self, cliente_id: int, direccion_id: int) -> bool:
        return bool(
            await self.uow.valor(
                """
                SELECT EXISTS (
                    SELECT 1 FROM direccion d JOIN zona_cobertura z ON z.id=d.zona_id
                    WHERE d.id = %s AND d.cliente_id = %s AND d.activa AND z.activa
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
        canal: str = "WEB",
        metodo_pago_acordado: str = "EFECTIVO",
    ) -> dict:
        subtotal = sum(
            (Decimal(str(item["precio_unitario"])) * item["cantidad"] for item in items),
            Decimal("0"),
        )
        costo_envio = (
            await self.costo_direccion(direccion_id) if tipo_entrega == "DELIVERY" else Decimal("0")
        )
        fila = await self.uow.uno(
            """
            INSERT INTO pedido
                (cliente_id, tipo_entrega, direccion_id, canal, estado,
                 subtotal, costo_envio, descuento_total, total, observaciones,metodo_pago_acordado)
            VALUES (%s, %s, %s, %s, 'PENDIENTE', %s, %s, 0, %s, %s,%s)
            RETURNING id
            """,
            (
                cliente_id,
                tipo_entrega,
                direccion_id,
                canal,
                subtotal,
                costo_envio,
                subtotal + costo_envio,
                observaciones,
                metodo_pago_acordado,
            ),
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

    async def costo_direccion(self, direccion_id: int) -> Decimal | None:
        return await self.uow.valor(
            "SELECT z.costo_envio FROM direccion d JOIN zona_cobertura z ON z.id=d.zona_id "
            "WHERE d.id=%s AND d.activa AND z.activa",
            (direccion_id,),
        )

    async def neto_cobrado(self, pedido_id: int) -> Decimal:
        return await self.uow.valor(
            "SELECT COALESCE(sum(CASE WHEN tipo='COBRO' THEN monto ELSE -monto END),0) "
            "FROM pago WHERE pedido_id=%s AND estado='CONCILIADO'",
            (pedido_id,),
        )

    async def editar_operacion(
        self,
        pedido_id: int,
        nuevos: dict,
        *,
        usuario_id: int | None,
        motivo: str,
        origen: str,
        anterior: dict,
    ) -> dict:
        campos = (
            "tipo_entrega",
            "direccion_id",
            "metodo_pago_acordado",
            "observaciones",
            "costo_envio",
            "total",
        )
        cambios = {
            campo: {"anterior": anterior.get(campo), "nuevo": nuevos.get(campo)}
            for campo in campos
            if anterior.get(campo) != nuevos.get(campo)
        }
        if not cambios:
            return await self.detalle(pedido_id)
        await self.uow.ejecutar(
            "UPDATE pedido SET tipo_entrega=%s,direccion_id=%s,metodo_pago_acordado=%s,"
            "observaciones=%s,costo_envio=%s,total=%s,version=version+1 WHERE id=%s",
            tuple(nuevos[campo] for campo in campos) + (pedido_id,),
        )
        await self.uow.ejecutar(
            "INSERT INTO pedido_estado_historial(pedido_id,estado_anterior,estado_nuevo,"
            "usuario_id,observacion,origen,version,cambios) "
            "SELECT id,estado,estado,%s,%s,%s,version,%s::jsonb FROM pedido WHERE id=%s",
            (usuario_id, motivo, origen, json.dumps(cambios, default=str), pedido_id),
        )
        await self.uow.ejecutar(
            "UPDATE whatsapp_borrador SET tipo_entrega=%s,metodo_pago=%s,"
            "direccion=(SELECT to_jsonb(d) FROM direccion d WHERE d.id=%s),version=version+1 "
            "WHERE pedido_id=%s",
            (
                nuevos["tipo_entrega"],
                nuevos["metodo_pago_acordado"],
                nuevos["direccion_id"],
                pedido_id,
            ),
        )
        return await self.detalle(pedido_id)

    async def listar(
        self,
        *,
        cliente_id: int | None,
        repartidor_id: int | None = None,
        q: str | None = None,
        estado: str | None = None,
        activos: bool | None = None,
    ) -> list[dict]:
        pedidos = await self.uow.todos(
            """
            SELECT p.id, p.numero, p.cliente_id,
                   COALESCE(NULLIF(concat_ws(' ', u.nombre, u.apellido), ''), c.nombre) AS cliente,
                   p.tipo_entrega, p.direccion_id, p.estado, p.subtotal,
                   p.costo_envio, p.total, p.observaciones, p.creado_en,
                   p.version,p.metodo_pago_acordado,p.confirmado_en,p.preparacion_en,
                   p.listo_en,p.entregado_en,p.cancelado_en,c.telefono_whatsapp AS telefono
            FROM pedido p
            JOIN cliente c ON c.id = p.cliente_id
            LEFT JOIN usuario u ON u.id = c.usuario_id
            WHERE (%s::bigint IS NULL OR p.cliente_id = %s)
              AND (%s::text IS NULL OR p.estado=%s)
              AND (%s::boolean IS NULL OR (p.estado NOT IN ('ENTREGADO','CANCELADO'))=%s)
              AND (%s::text IS NULL OR concat_ws(' ',p.numero,c.nombre,u.nombre,u.apellido,
                  c.telefono_whatsapp,p.observaciones) ILIKE '%%' || %s || '%%')
              AND (%s::bigint IS NULL OR EXISTS (
                  SELECT 1 FROM envio e JOIN viaje v ON v.id = e.viaje_id
                  WHERE e.pedido_id = p.id AND v.repartidor_id = %s
                    AND v.estado IN ('PLANIFICADO', 'EN_RUTA')
                    AND e.estado IN ('ASIGNADO', 'EN_CAMINO')
              ))
            ORDER BY p.creado_en DESC, p.id DESC
            """,
            (
                cliente_id,
                cliente_id,
                estado,
                estado,
                activos,
                activos,
                q,
                q,
                repartidor_id,
                repartidor_id,
            ),
        )
        await self._completar(pedidos)
        return pedidos

    async def detalle(self, pedido_id: int) -> dict:
        pedido = await self.uow.uno(
            """
            SELECT p.id, p.numero, p.cliente_id,
                   COALESCE(NULLIF(concat_ws(' ', u.nombre, u.apellido), ''), c.nombre) AS cliente,
                   p.tipo_entrega, p.direccion_id, p.estado, p.subtotal,
                   p.costo_envio, p.total, p.observaciones, p.creado_en,
                   p.version, p.metodo_pago_acordado, p.confirmado_en,
                   p.preparacion_en, p.listo_en, p.entregado_en, p.cancelado_en,
                   c.telefono_whatsapp AS telefono
            FROM pedido p
            JOIN cliente c ON c.id = p.cliente_id
            LEFT JOIN usuario u ON u.id = c.usuario_id
            WHERE p.id = %s
            """,
            (pedido_id,),
        )
        if pedido is None:
            return None
        await self._completar([pedido])
        return pedido

    async def _completar(self, pedidos: list[dict]) -> None:
        """Carga las relaciones en bloque, con seis consultas para cualquier listado."""
        if not pedidos:
            return
        por_id = {pedido["id"]: pedido for pedido in pedidos}
        ids = list(por_id)
        for pedido in pedidos:
            pedido.update(items=[], historial=[], pagos=[], direccion=None, envio=None)
        items = await self.uow.todos(
            "SELECT * FROM pedido_item WHERE pedido_id=ANY(%s) ORDER BY id", (ids,)
        )
        for item in items:
            por_id[item["pedido_id"]]["items"].append(item)
        direcciones = await self.uow.todos(
            "SELECT p.id AS pedido_id,d.id,d.calle,d.numero,d.localidad,d.referencia,d.zona_id "
            "FROM pedido p JOIN direccion d ON d.id=p.direccion_id WHERE p.id=ANY(%s)",
            (ids,),
        )
        for direccion in direcciones:
            por_id[direccion.pop("pedido_id")]["direccion"] = direccion
        envios = await self.uow.todos(
            "SELECT e.*,v.repartidor_id,v.estado AS estado_viaje,v.salida_en "
            "FROM envio e LEFT JOIN viaje v ON v.id=e.viaje_id WHERE e.pedido_id=ANY(%s)",
            (ids,),
        )
        for envio in envios:
            por_id[envio["pedido_id"]]["envio"] = envio
        historial = await self.uow.todos(
            "SELECT h.*,concat_ws(' ',u.nombre,u.apellido) AS actor "
            "FROM pedido_estado_historial h LEFT JOIN usuario u ON u.id=h.usuario_id "
            "WHERE h.pedido_id=ANY(%s) ORDER BY h.creado_en,h.id",
            (ids,),
        )
        for evento in historial:
            por_id[evento["pedido_id"]]["historial"].append(evento)
        pagos = await self.uow.todos(
            "SELECT id,pedido_id,tipo,metodo_pago,monto,estado,registrado_en,conciliado_en "
            "FROM pago WHERE pedido_id=ANY(%s) ORDER BY id",
            (ids,),
        )
        for pago in pagos:
            por_id[pago["pedido_id"]]["pagos"].append(pago)
        for pedido in pedidos:
            pedido["neto_cobrado"] = sum(
                (
                    (p["monto"] if p["tipo"] == "COBRO" else -p["monto"])
                    for p in pedido["pagos"]
                    if p["estado"] == "CONCILIADO"
                ),
                Decimal("0"),
            )
            pedido["saldo_pendiente"] = max(Decimal("0"), pedido["total"] - pedido["neto_cobrado"])

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
            # READ COMMITTED fija el snapshot al comenzar cada sentencia. Si
            # esperamos aqui, el siguiente SELECT ve los pagos/envios que el
            # productor confirmo mientras retenia el mismo bloqueo del pedido.
            # Mezclar estos indicadores con FOR UPDATE conservaria el snapshot
            # anterior a la espera cuando el productor no actualiza pedido.
            bloqueado = await self.uow.uno(
                "SELECT id FROM pedido WHERE id=%s FOR UPDATE", (pedido_id,)
            )
            if bloqueado is None:
                return None
            return await self.uow.uno(
                """
                SELECT p.*,
                       (p.metodo_pago_acordado='EFECTIVO' OR p.total <= (
                           SELECT COALESCE(sum(CASE WHEN tipo='COBRO' THEN monto ELSE -monto END),0)
                           FROM pago WHERE pedido_id=p.id AND estado='CONCILIADO'
                       )) AS puede_preparar,
                       EXISTS(SELECT 1 FROM envio e JOIN viaje v ON v.id=e.viaje_id
                           WHERE e.pedido_id=p.id AND v.estado IN ('PLANIFICADO','EN_RUTA'))
                           AS asignado,
                       EXISTS(SELECT 1 FROM envio e WHERE e.pedido_id=p.id
                           AND e.viaje_id IS NOT NULL) AS vinculo_logistico,
                       EXISTS(SELECT 1 FROM envio e JOIN viaje v ON v.id=e.viaje_id
                           WHERE e.pedido_id=p.id AND e.estado='EN_CAMINO'
                           AND v.estado='EN_RUTA' AND v.salida_en IS NOT NULL) AS salida_real,
                       EXISTS(SELECT 1 FROM envio e JOIN viaje v ON v.id=e.viaje_id
                           WHERE e.pedido_id=p.id AND e.estado='ENTREGADO'
                           AND v.salida_en IS NOT NULL) AS entrega_real
                FROM pedido p WHERE p.id = %s
                """,
                (pedido_id,),
            )
        return await self.uow.uno("SELECT * FROM pedido WHERE id = %s", (pedido_id,))

    async def items_para_stock(self, pedido_id: int) -> list[dict]:
        return await self.uow.todos(
            "SELECT producto_id, cantidad, aclaraciones FROM pedido_item "
            "WHERE pedido_id = %s ORDER BY id",
            (pedido_id,),
        )

    async def cambiar_estado(
        self,
        pedido_id: int,
        estado: EstadoPedido,
        usuario_id: int | None,
        *,
        motivo: str | None = None,
        origen: str = "PANEL",
        tratamiento_stock: str | None = None,
    ) -> dict:
        anterior = await self.uow.valor("SELECT estado FROM pedido WHERE id = %s", (pedido_id,))
        await self.uow.ejecutar(
            """UPDATE pedido SET estado=%s,version=version+1,
                confirmado_en=CASE WHEN %s IN ('CONFIRMADO','EN_PREPARACION')
                    THEN COALESCE(confirmado_en,now()) ELSE confirmado_en END,
                preparacion_en=CASE WHEN %s='EN_PREPARACION' THEN now() ELSE preparacion_en END,
                listo_en=CASE WHEN %s='LISTO' THEN now() ELSE listo_en END,
                entregado_en=CASE WHEN %s='ENTREGADO' THEN now() ELSE entregado_en END,
                cancelado_en=CASE WHEN %s='CANCELADO' THEN now() ELSE cancelado_en END,
                motivo_cancelacion=CASE WHEN %s='CANCELADO' THEN %s ELSE motivo_cancelacion END
            WHERE id=%s""",
            (
                estado.value,
                estado.value,
                estado.value,
                estado.value,
                estado.value,
                estado.value,
                estado.value,
                motivo,
                pedido_id,
            ),
        )
        await self.uow.ejecutar(
            """
            INSERT INTO pedido_estado_historial
                (pedido_id, estado_anterior, estado_nuevo, usuario_id, observacion,
                 origen,version,tratamiento_stock)
            VALUES (%s,%s,%s,%s,%s,%s,(SELECT version FROM pedido WHERE id=%s),%s)
            """,
            (
                pedido_id,
                anterior,
                estado.value,
                usuario_id,
                motivo or "Avance de estado",
                origen,
                pedido_id,
                tratamiento_stock,
            ),
        )
        return await self.detalle(pedido_id)
