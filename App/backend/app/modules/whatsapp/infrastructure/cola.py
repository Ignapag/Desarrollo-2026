"""Reclamo corto de mensajes; nunca conserva conexiones durante el envío."""

from app.core.db import UnidadDeTrabajo
from app.modules.whatsapp.domain.mensajes import ocultar_referencias


class ColaWhatsAppSQL:
    def __init__(self, uow: UnidadDeTrabajo):
        self.uow = uow

    async def pendientes(self, limite=20, *, solo_demo=False):
        return await self.uow.todos(
            "SELECT id,texto,telefono FROM whatsapp_entrada WHERE estado='PENDIENTE' "
            "AND (NOT %s OR EXISTS(SELECT 1 FROM chat_demo_sesion d "
            "WHERE d.telefono=whatsapp_entrada.telefono)) "
            "ORDER BY creado_en,orden_recibido LIMIT %s",
            (solo_demo, limite),
        )

    async def reclamar(self, *, solo_demo=False):
        # Un proceso caído pudo haber enviado: no volver a enviar sin evidencia.
        await self.uow.ejecutar(
            """UPDATE whatsapp_salida SET estado='INCIERTO',actualizado_en=now()
            WHERE estado='ENVIANDO' AND actualizado_en<now()-interval '5 minutes'
            AND (NOT %s OR EXISTS(SELECT 1 FROM chat_demo_sesion d
                WHERE d.telefono=whatsapp_salida.telefono))""",
            (solo_demo,),
        )
        return await self.uow.uno(
            """UPDATE whatsapp_salida SET estado='ENVIANDO',intentos=intentos+1,
            actualizado_en=now() WHERE id=(
                SELECT id FROM whatsapp_salida
                WHERE estado IN ('PENDIENTE','FALLIDO') AND intentos<3 AND proximo_intento_en<=now()
                AND (NOT %s OR EXISTS(SELECT 1 FROM chat_demo_sesion d
                    WHERE d.telefono=whatsapp_salida.telefono))
                ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1
            ) RETURNING *""",
            (solo_demo,),
        )

    async def dentro_ventana(self, telefono):
        return bool(
            await self.uow.valor(
                """SELECT EXISTS (SELECT 1 FROM whatsapp_entrada WHERE telefono=%s
            AND creado_en>now()-interval '24 hours')""",
                (telefono,),
            )
        )

    async def resultado(self, identificador, estado, proveedor_id=None):
        if proveedor_id:
            await self.uow.valor(
                "SELECT pg_advisory_xact_lock(hashtext(%s))", ("envio:" + proveedor_id,)
            )
        await self.uow.ejecutar(
            """UPDATE whatsapp_salida SET estado=%s,proveedor_id=%s,actualizado_en=now(),
            proximo_intento_en=now()+make_interval(secs=>60*power(2,intentos)::int)
            WHERE id=%s AND estado='ENVIANDO'""",
            (estado, proveedor_id, identificador),
        )
        if proveedor_id:
            await self._reconciliar(proveedor_id)

    async def estado_proveedor(self, proveedor_id, telefono, estado):
        if estado not in {"sent", "delivered", "read", "failed"}:
            return
        await self.uow.valor(
            "SELECT pg_advisory_xact_lock(hashtext(%s))", ("envio:" + proveedor_id,)
        )
        await self.uow.ejecutar(
            """INSERT INTO whatsapp_estado_envio (proveedor_id,telefono,estado)
            VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",
            (proveedor_id, telefono, estado),
        )
        await self._reconciliar(proveedor_id)

    async def _reconciliar(self, proveedor_id):
        # No se degrada una entrega probada por un evento tardío o repetido.
        await self.uow.ejecutar(
            """UPDATE whatsapp_salida s SET estado=e.estado,actualizado_en=now(),
            intentos=CASE WHEN e.estado='FALLIDO' THEN 3 ELSE s.intentos END
            FROM (
                SELECT proveedor_id,telefono,
                CASE WHEN bool_or(estado IN ('delivered','read')) THEN 'ENTREGADO'
                     WHEN bool_or(estado='failed') THEN 'FALLIDO' ELSE 'ACEPTADO' END estado
                FROM whatsapp_estado_envio WHERE proveedor_id=%s GROUP BY proveedor_id,telefono
            ) e WHERE s.proveedor_id=e.proveedor_id AND s.telefono=e.telefono
            AND s.estado IN ('ACEPTADO','INCIERTO','FALLIDO')""",
            (proveedor_id,),
        )

    async def avisos(self):
        """Sólo cantidades pendientes; no descarga historial ni datos de clientes."""
        return await self.uow.uno(
            """SELECT
            (SELECT count(*) FROM whatsapp_comprobante WHERE estado='PENDIENTE') +
            (SELECT count(*) FROM whatsapp_atencion
                WHERE estado='PENDIENTE' AND motivo='COMPROBANTE')
                comprobantes_pendientes,
            (SELECT count(*) FROM whatsapp_atencion
                WHERE estado='PENDIENTE' AND motivo<>'COMPROBANTE')
                atenciones_pendientes"""
        )

    async def bandeja(self):
        comprobantes = await self.uow.todos(
            """SELECT c.id,c.pedido_id,p.numero,p.total,b.metodo_pago,
            c.estado,c.creado_en,c.revisado_por,c.motivo
            FROM whatsapp_comprobante c JOIN pedido p ON p.id=c.pedido_id
            JOIN whatsapp_borrador b ON b.pedido_id=p.id
            ORDER BY (c.estado='PENDIENTE') DESC,c.creado_en DESC LIMIT 100"""
        )
        cambios = await self.uow.todos(
            "SELECT * FROM whatsapp_cambio WHERE estado='PENDIENTE_EMPLEADO' ORDER BY id LIMIT 100"
        )
        salidas = await self.uow.todos(
            "SELECT id,estado,intentos,actualizado_en FROM whatsapp_salida "
            "ORDER BY id DESC LIMIT 100"
        )
        return {
            "comprobantes": comprobantes,
            "cambios": cambios,
            "atenciones": await self._atenciones(),
            "salidas": salidas,
        }

    async def _atenciones(self):
        """Derivaciones pendientes con lo necesario para contactar y resolver."""
        atenciones = await self.uow.todos(
            """WITH pendientes AS (
                (SELECT * FROM whatsapp_atencion
                 WHERE estado='PENDIENTE' AND motivo='COMPROBANTE'
                 ORDER BY creado_en,id LIMIT 100)
                UNION ALL
                (SELECT * FROM whatsapp_atencion
                 WHERE estado='PENDIENTE' AND motivo<>'COMPROBANTE'
                 ORDER BY creado_en,id LIMIT 100)
            )
            SELECT a.id,a.referencia_hash,a.motivo,a.estado,a.creado_en,a.entrada_id,
            COALESCE(a.telefono,b.telefono) telefono,
            b.estado estado_conversacion,b.tipo_entrega,b.metodo_pago,b.items,
            b.pedido_id,b.contexto_chat,
            (b.pedido_id IS NULL AND b.expira_en<=now()) borrador_vencido,
            p.numero,p.estado estado_pedido,p.total,
            COALESCE(NULLIF(concat_ws(' ',u.nombre,u.apellido), ''), c.nombre,
                e.nombre_remitente) cliente,
            e.texto mensaje,e.media_id IS NOT NULL tiene_archivo
            FROM pendientes a
            LEFT JOIN whatsapp_borrador b ON b.referencia_hash=a.referencia_hash
            JOIN whatsapp_entrada e ON e.id=a.entrada_id
            LEFT JOIN cliente c ON c.id=b.cliente_id
            LEFT JOIN usuario u ON u.id=c.usuario_id
            LEFT JOIN pedido p ON p.id=b.pedido_id
            ORDER BY a.creado_en,a.id"""
        )
        if not atenciones:
            return []
        hashes = [a["referencia_hash"] for a in atenciones]
        mensajes = await self.uow.todos(
            """SELECT referencia_hash,texto,respuesta,creado_en FROM (
                SELECT referencia_hash,texto,respuesta,creado_en,row_number() OVER (
                    PARTITION BY referencia_hash ORDER BY creado_en DESC, id DESC) n
                FROM whatsapp_entrada WHERE referencia_hash = ANY(%s)
            ) m WHERE n<=5 ORDER BY creado_en, texto""",
            (hashes,),
        )
        items_pedido = await self.uow.todos(
            """SELECT pedido_id,nombre_producto nombre,cantidad,aclaraciones FROM pedido_item
            WHERE pedido_id = ANY(%s) ORDER BY id""",
            ([a["pedido_id"] for a in atenciones if a["pedido_id"]],),
        )
        nombres = {
            fila["id"]: fila["nombre"]
            for fila in await self.uow.todos(
                "SELECT id,nombre FROM producto WHERE id = ANY(%s)",
                (sorted({i["producto_id"] for a in atenciones for i in (a["items"] or [])}),),
            )
        }
        respuestas = await self.uow.todos(
            """SELECT s.atencion_id,s.id,s.texto,s.estado,s.intentos,s.actualizado_en,
            concat_ws(' ',u.nombre,u.apellido) empleado
            FROM whatsapp_salida s JOIN usuario u ON u.id=s.enviado_por
            WHERE s.atencion_id = ANY(%s) ORDER BY s.id""",
            ([a["id"] for a in atenciones],),
        )
        for a in atenciones:
            hash_conversacion = a.pop("referencia_hash")
            items_borrador = a.pop("items") or []
            # El personal ve el mensaje completo; nunca la referencia de acceso.
            a["mensaje"] = ocultar_referencias(a["mensaje"])
            chat = a.pop("contexto_chat") or {}
            origen = a.pop("entrada_id")
            if chat.get("bloqueo_operativo"):
                a["mensaje"] += "\n\n" + chat["bloqueo_operativo"]
            if a["motivo"] == "SOLICITUD" and (
                chat.get("solicitud_id") == origen
                or chat.get("pregunta") in {"direccion", "numero", "localidad"}
            ):
                datos = chat.get("datos") or {}
                detalle = [
                    f"{etiqueta}: {datos[campo]}"
                    for campo, etiqueta in (
                        ("direccion", "Calle"),
                        ("numero", "Número"),
                        ("localidad", "Localidad"),
                        ("referencias", "Referencia"),
                        ("tipo_entrega", "Entrega solicitada"),
                        ("metodo_pago", "Pago solicitado"),
                    )
                    if isinstance(datos.get(campo), str)
                ]
                if detalle:
                    a["mensaje"] += (
                        "\n\nDatos solicitados por el cliente (sin aplicar):\n"
                        + "\n".join(ocultar_referencias(d) for d in detalle)
                    )
            a["mensajes"] = [
                {
                    "texto": ocultar_referencias(m["texto"]),
                    "respuesta": m["respuesta"],
                    "creado_en": m["creado_en"],
                }
                for m in mensajes
                if m["referencia_hash"] == hash_conversacion
            ]
            if hash_conversacion is None:
                # Sin compra elegida sólo mostrar el mensaje origen, nunca buscar
                # una compra ni su historial por el teléfono de contacto declarado.
                a["mensajes"] = []
            if a["pedido_id"]:
                a["productos"] = [
                    {k: i[k] for k in ("nombre", "cantidad", "aclaraciones")}
                    for i in items_pedido
                    if i["pedido_id"] == a["pedido_id"]
                ]
            else:
                a["productos"] = [
                    {
                        "nombre": nombres.get(i["producto_id"], f"Producto {i['producto_id']}")
                        + (f" ({i['variante']})" if i.get("variante") else ""),
                        "cantidad": i["cantidad"],
                        "aclaraciones": i.get("aclaraciones"),
                    }
                    for i in items_borrador
                ]
            a["respuestas"] = [
                {k: v for k, v in r.items() if k != "atencion_id"}
                for r in respuestas
                if r["atencion_id"] == a["id"]
            ]
        return atenciones
