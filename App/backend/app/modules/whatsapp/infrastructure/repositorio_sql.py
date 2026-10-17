"""Inbox, borradores, revisión y outbox en la unidad de trabajo del caso de uso."""

from datetime import UTC, datetime

from psycopg.types.json import Jsonb

from app.core.db import UnidadDeTrabajo


class RepositorioBotSQL:
    def __init__(self, uow: UnidadDeTrabajo):
        self.uow = uow

    async def crear_borrador(self, referencia_hash, cliente_id, datos):
        return await self.uow.uno(
            """INSERT INTO whatsapp_borrador
            (referencia_hash,cliente_id,telefono,items,tipo_entrega,metodo_pago,direccion,contacto)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (
                referencia_hash,
                cliente_id,
                datos.get("telefono") if cliente_id is not None else None,
                Jsonb(datos["items"]),
                datos.get("tipo_entrega"),
                datos.get("metodo_pago"),
                Jsonb(datos.get("direccion_nueva")),
                Jsonb(datos.get("contacto") or {}),
            ),
        )

    async def recibir(self, identificador, telefono, texto, media_id, nombre_remitente=None):
        await self.uow.ejecutar(
            """INSERT INTO whatsapp_entrada (id,telefono,texto,media_id,nombre_remitente)
            VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
            (identificador, telefono, texto, media_id, nombre_remitente),
        )

    async def entrada(self, identificador, bloquear=False):
        sql = "SELECT * FROM whatsapp_entrada WHERE id=%s"
        if bloquear:
            sql += " FOR UPDATE"
        return await self.uow.uno(sql, (identificador,))

    async def conversacion(
        self, telefono, referencia_hash=None, bloquear=False, nombre_remitente=None
    ):
        # Todas las mutaciones de una conversación se serializan también entre workers.
        if bloquear:
            await self.uow.valor("SELECT pg_advisory_xact_lock(hashtext(%s))", (telefono,))
        if referencia_hash:
            sql = """SELECT * FROM whatsapp_borrador WHERE referencia_hash=%s
                AND (telefono=%s OR telefono IS NULL)"""
            params = (referencia_hash, telefono)
        else:
            sql = """SELECT * FROM whatsapp_borrador WHERE telefono=%s
                AND ultimo_mensaje_en IS NOT NULL
                AND (pedido_id IS NOT NULL OR expira_en>now())
                AND (pedido_id IS NULL OR EXISTS (
                    SELECT 1 FROM pedido p WHERE p.id=pedido_id
                    AND p.estado NOT IN ('ENTREGADO','CANCELADO')
                ))
                ORDER BY ultimo_mensaje_en DESC LIMIT 2"""
            params = (telefono,)
        if bloquear:
            sql += " FOR UPDATE"
        filas = await self.uow.todos(sql, params)
        # Una conversación con dos pedidos requiere una referencia explícita.
        if len(filas) != 1:
            return None
        b = filas[0]
        if bloquear and b["telefono"] is None and b["expira_en"] > datetime.now(UTC):
            # Bajo el bloqueo del teléfono y de la referencia: dos workers no
            # pueden reclamarla para remitentes distintos ni duplicar al cliente.
            cliente_id = await self.uow.valor(
                "SELECT id FROM cliente WHERE whatsapp_verificado=%s", (telefono,)
            )
            contacto = b.get("contacto") or {}
            nombre_contacto = " ".join(
                contacto.get(campo, "") for campo in ("nombre", "apellido")
            ).strip()
            if cliente_id is None:
                cliente_id = await self.uow.valor(
                    """INSERT INTO cliente
                    (nombre,telefono_whatsapp,whatsapp_verificado,telefono_contacto)
                    VALUES (%s,%s,%s,%s) RETURNING id""",
                    (
                        nombre_contacto or nombre_remitente or f"WhatsApp {telefono}",
                        telefono,
                        telefono,
                        contacto.get("telefono"),
                    ),
                )
            elif nombre_contacto:
                await self.uow.ejecutar(
                    "UPDATE cliente SET nombre=%s,telefono_contacto=%s WHERE id=%s",
                    (nombre_contacto, contacto.get("telefono"), cliente_id),
                )
            await self.uow.ejecutar(
                """UPDATE whatsapp_borrador SET telefono=%s,cliente_id=%s
                WHERE referencia_hash=%s""",
                (telefono, cliente_id, b["referencia_hash"]),
            )
            b.update(telefono=telefono, cliente_id=cliente_id)
        return b

    async def actualizar_borrador(self, b):
        await self.uow.ejecutar(
            """UPDATE whatsapp_borrador SET items=%s,tipo_entrega=%s,metodo_pago=%s,direccion=%s,
            estado=%s,pedido_id=%s,version=%s,propuesta=%s,estado_pago=%s,ultimo_mensaje_en=now()
            WHERE referencia_hash=%s""",
            (
                Jsonb(b["items"]),
                b["tipo_entrega"],
                b["metodo_pago"],
                Jsonb(b["direccion"]),
                b["estado"],
                b["pedido_id"],
                b["version"],
                Jsonb(b["propuesta"]),
                b["estado_pago"],
                b["referencia_hash"],
            ),
        )

    async def finalizar(self, entrada, b, respuesta):
        if b:
            await self.actualizar_borrador(b)
        await self.uow.ejecutar(
            """UPDATE whatsapp_entrada SET estado='PROCESADO',respuesta=%s,referencia_hash=%s
            WHERE id=%s""",
            (respuesta, b["referencia_hash"] if b else None, entrada["id"]),
        )
        await self.encolar("respuesta:" + entrada["id"], entrada["telefono"], respuesta)

    async def encolar(self, clave, telefono, texto):
        await self.uow.ejecutar(
            """INSERT INTO whatsapp_salida (clave,telefono,texto) VALUES (%s,%s,%s)
            ON CONFLICT (clave) DO NOTHING""",
            (clave, telefono, texto),
        )

    async def pedido(self, pedido_id):
        pedido = await self.uow.uno("SELECT * FROM pedido WHERE id=%s FOR UPDATE", (pedido_id,))
        pedido["items"] = await self.uow.todos(
            "SELECT * FROM pedido_item WHERE pedido_id=%s ORDER BY id", (pedido_id,)
        )
        pedido["pagado"] = await self.uow.valor(
            """SELECT COALESCE(sum(CASE WHEN tipo='COBRO' THEN monto ELSE -monto END),0)
            FROM pago WHERE pedido_id=%s AND estado='CONCILIADO'""",
            (pedido_id,),
        )
        pedido["stock_consumido"] = await self.uow.valor(
            "SELECT EXISTS (SELECT 1 FROM movimiento_stock WHERE pedido_id=%s AND tipo='CONSUMO')",
            (pedido_id,),
        )
        return pedido

    async def ingredientes(self, producto_id):
        return await self.uow.todos(
            """SELECT i.nombre, pi.es_base FROM producto_ingrediente pi
            JOIN ingrediente i ON i.id=pi.ingrediente_id WHERE pi.producto_id=%s
            ORDER BY i.nombre, i.id""",
            (producto_id,),
        )

    async def historial(self, b, accion, anterior, posterior, estado, empleado_id=None):
        return await self.uow.uno(
            """INSERT INTO whatsapp_cambio
            (pedido_id,version,accion,anterior,posterior,estado,revisado_por,revisado_en)
            VALUES (%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s::bigint IS NULL THEN NULL ELSE now() END)
            RETURNING id""",
            (
                b["pedido_id"],
                b["version"],
                Jsonb(accion),
                Jsonb(anterior),
                Jsonb(posterior),
                estado,
                empleado_id,
                empleado_id,
            ),
        )

    async def aplicar_item(self, pedido, item, cantidad, aclaraciones):
        await self.uow.ejecutar(
            """UPDATE pedido_item SET cantidad=%s,aclaraciones=%s,
            subtotal=(precio_unitario+costo_opciones)*%s WHERE id=%s""",
            (cantidad, aclaraciones, cantidad, item["id"]),
        )
        await self.uow.ejecutar(
            """UPDATE pedido SET subtotal=s.subtotal,
            total=s.subtotal+costo_envio-descuento_total FROM
            (SELECT sum(subtotal) subtotal FROM pedido_item WHERE pedido_id=%s) s
            WHERE pedido.id=%s""",
            (pedido["id"], pedido["id"]),
        )

    async def comprobante(self, entrada, pedido_id):
        await self.uow.ejecutar(
            """INSERT INTO whatsapp_comprobante (entrada_id,pedido_id,media_id)
            VALUES (%s,%s,%s) ON CONFLICT (entrada_id) DO NOTHING""",
            (entrada["id"], pedido_id, entrada["media_id"]),
        )

    async def revision(self, comprobante_id):
        # Bot y revisiones: borrador -> pedido -> comprobante. Preparación solo toma pedido.
        fila = await self.uow.uno(
            "SELECT * FROM whatsapp_comprobante WHERE id=%s", (comprobante_id,)
        )
        if not fila:
            return None
        await self.uow.uno(
            "SELECT referencia_hash FROM whatsapp_borrador WHERE pedido_id=%s FOR UPDATE",
            (fila["pedido_id"],),
        )
        await self.uow.uno("SELECT id FROM pedido WHERE id=%s FOR UPDATE", (fila["pedido_id"],))
        return await self.uow.uno(
            "SELECT * FROM whatsapp_comprobante WHERE id=%s FOR UPDATE", (comprobante_id,)
        )

    async def revisar(self, comprobante, aprobar, empleado_id, motivo):
        pedido = await self.pedido(comprobante["pedido_id"])
        estado = "APROBADO" if aprobar else "RECHAZADO"
        await self.uow.ejecutar(
            """UPDATE whatsapp_comprobante SET estado=%s,revisado_por=%s,
            revisado_en=now(),motivo=%s WHERE id=%s""",
            (estado, empleado_id, motivo, comprobante["id"]),
        )
        await self.uow.ejecutar(
            """UPDATE whatsapp_borrador SET estado_pago=CASE
            WHEN estado_pago='APROBADO' THEN estado_pago ELSE %s END WHERE pedido_id=%s""",
            (estado, pedido["id"]),
        )
        saldo = pedido["total"] - pedido["pagado"]
        if aprobar and saldo > 0:
            await self.uow.ejecutar(
                """INSERT INTO pago
                (pedido_id,tipo,metodo_pago,monto,estado,registrado_por,conciliado_en,
                 referencia_externa,motivo)
                VALUES (%s,'COBRO','TRANSFERENCIA',%s,'CONCILIADO',%s,now(),%s,%s)""",
                (pedido["id"], saldo, empleado_id, f"comprobante:{comprobante['id']}", motivo),
            )
        telefono = await self.uow.valor(
            "SELECT telefono FROM whatsapp_borrador WHERE pedido_id=%s", (pedido["id"],)
        )
        await self.encolar(
            f"revision:{comprobante['id']}",
            telefono,
            f"Pedido #{pedido['numero']}: transferencia {estado.lower()} por personal.",
        )
        return {"id": comprobante["id"], "estado": estado, "pedido_id": pedido["id"]}

    async def cambio(self, cambio_id):
        fila = await self.uow.uno("SELECT * FROM whatsapp_cambio WHERE id=%s", (cambio_id,))
        if not fila:
            return None, None
        b = await self.uow.uno(
            "SELECT * FROM whatsapp_borrador WHERE pedido_id=%s FOR UPDATE", (fila["pedido_id"],)
        )
        fila = await self.uow.uno(
            "SELECT * FROM whatsapp_cambio WHERE id=%s FOR UPDATE", (cambio_id,)
        )
        return fila, b

    async def cerrar_cambio(self, cambio_id, estado, empleado_id, motivo):
        await self.uow.ejecutar(
            """UPDATE whatsapp_cambio SET estado=%s,revisado_por=%s,revisado_en=now(),
            accion=accion || jsonb_build_object('revision_motivo',%s::text) WHERE id=%s""",
            (estado, empleado_id, motivo, cambio_id),
        )

    async def derivar(self, referencia_hash, entrada_id, motivo):
        # A lo sumo una atención pendiente por conversación; la nueva solicitud queda
        # en el historial de mensajes que la bandeja muestra junto a la atención.
        await self.uow.ejecutar(
            """INSERT INTO whatsapp_atencion (referencia_hash,entrada_id,motivo)
            VALUES (%s,%s,%s)
            ON CONFLICT (referencia_hash) WHERE estado='PENDIENTE' DO NOTHING""",
            (referencia_hash, entrada_id, motivo),
        )

    async def atencion_pendiente(self, referencia_hash):
        return bool(
            await self.uow.valor(
                """SELECT EXISTS (SELECT 1 FROM whatsapp_atencion
                WHERE referencia_hash=%s AND estado='PENDIENTE')""",
                (referencia_hash,),
            )
        )

    async def atencion(self, atencion_id, bloquear=False):
        fila = await self.uow.uno(
            """SELECT a.*,b.telefono FROM whatsapp_atencion a
            JOIN whatsapp_borrador b ON b.referencia_hash=a.referencia_hash WHERE a.id=%s""",
            (atencion_id,),
        )
        if not fila or not bloquear:
            return fila
        # Mismo orden que el bot: teléfono -> conversación -> atención.
        await self.uow.valor("SELECT pg_advisory_xact_lock(hashtext(%s))", (fila["telefono"],))
        await self.uow.uno(
            "SELECT referencia_hash FROM whatsapp_borrador WHERE referencia_hash=%s FOR UPDATE",
            (fila["referencia_hash"],),
        )
        return await self.uow.uno(
            """SELECT a.*,b.telefono FROM whatsapp_atencion a
            JOIN whatsapp_borrador b ON b.referencia_hash=a.referencia_hash
            WHERE a.id=%s FOR UPDATE OF a""",
            (atencion_id,),
        )

    async def respuesta_atencion(self, clave):
        return await self.uow.uno(
            "SELECT id,atencion_id,estado FROM whatsapp_salida WHERE clave=%s", (clave,)
        )

    async def encolar_respuesta(self, clave, atencion, texto, empleado_id):
        return await self.uow.uno(
            """INSERT INTO whatsapp_salida (clave,telefono,texto,atencion_id,enviado_por)
            VALUES (%s,%s,%s,%s,%s) RETURNING id,atencion_id,estado""",
            (clave, atencion["telefono"], texto, atencion["id"], empleado_id),
        )

    async def resolver_atencion(self, atencion, empleado_id, resolucion):
        await self.uow.ejecutar(
            """UPDATE whatsapp_atencion SET estado='RESUELTA',resolucion=%s,
            resuelta_por=%s,resuelta_en=now() WHERE id=%s""",
            (resolucion, empleado_id, atencion["id"]),
        )
        # La conversación vuelve al bot salvo que siga esperando un cambio del personal.
        await self.uow.ejecutar(
            """UPDATE whatsapp_borrador b SET estado=CASE
                WHEN b.pedido_id IS NULL THEN 'VINCULADO' ELSE 'CREADO' END
            WHERE b.referencia_hash=%s AND b.estado='HUMANO' AND NOT EXISTS (
                SELECT 1 FROM whatsapp_cambio c
                WHERE c.pedido_id=b.pedido_id AND c.estado='PENDIENTE_EMPLEADO'
            )""",
            (atencion["referencia_hash"],),
        )

    async def saldo_pedido(self, pedido_id):
        return await self.uow.valor("SELECT total FROM pedido WHERE id=%s", (pedido_id,))
