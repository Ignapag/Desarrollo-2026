"""Repositorio SQL parametrizado de pedidos."""

import hashlib
import json
import re
from decimal import Decimal

from app.core.db import UnidadDeTrabajo
from app.errores import ReglaDeNegocio
from app.modules.pedidos.domain.entidades import EstadoPedido
from app.modules.stock.application.servicio_stock import StockInsuficiente
from app.modules.stock.domain.entidades import ingredientes_omitidos_de_aclaraciones

# Letras con tilde y su base; el SQL del buscador aplica la misma equivalencia.
_CON_TILDE = "áàäâéèëêíìïîóòöôúùüûñçÁÀÄÂÉÈËÊÍÌÏÎÓÒÖÔÚÙÜÛÑÇ"
_SIN_TILDE = "aaaaeeeeiiiioooouuuuncaaaaeeeeiiiioooouuuunc"
_QUITAR_TILDES = str.maketrans(_CON_TILDE, _SIN_TILDE)
# Con menos dígitos, un número de pedido coincidiría con cualquier teléfono que los contenga.
_MIN_DIGITOS_TELEFONO = 6


def terminos_busqueda(q: str | None) -> tuple[str | None, str | None]:
    """Interpreta el texto del buscador de pedidos tal como lo escribe el personal.

    Quita el prefijo «Pedido #» o «#», ignora mayúsculas y tildes y escapa los comodines
    de LIKE para que «%» o «_» se busquen literalmente. Devuelve el texto normalizado y,
    si trae al menos seis dígitos, esos dígitos sin formato para comparar teléfonos
    («+54 9 221 555-1234» encuentra 5492215551234). ``(None, None)`` desactiva el filtro.
    """
    texto = re.sub(r"^(?:pedido\s*)?#\s*", "", (q or "").strip(), flags=re.IGNORECASE)
    texto = texto.strip().lower().translate(_QUITAR_TILDES)
    if not texto:
        return None, None
    digitos = re.sub(r"\D", "", texto)
    escapado = texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return escapado, digitos if len(digitos) >= _MIN_DIGITOS_TELEFONO else None


class RepositorioPedidosSQL:
    """Acceso SQL a pedidos, sus ítems, direcciones, historial y datos de cobro."""

    def __init__(self, uow: UnidadDeTrabajo) -> None:
        """Recibe la unidad de trabajo cuya transacción comparten las consultas."""
        self.uow = uow

    async def cliente_valido(self, cliente_id: int) -> bool:
        """Indica si el cliente existe, está activo y, si tiene cuenta, esta también."""
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

    async def extras_producto(self, producto_id: int, variante: str | None) -> list[dict]:
        """Opciones activas que pertenecen a la receta efectiva, sin Dips Extra."""
        return await self.uow.todos(
            """SELECT o.ingrediente_id,i.nombre,i.unidad_medida,o.cantidad_requerida,
                      o.costo_adicional AS precio,o.max_por_item
               FROM producto_opcion o JOIN ingrediente i ON i.id=o.ingrediente_id
               JOIN producto p ON p.id=o.producto_id JOIN categoria c ON c.id=p.categoria_id
               WHERE o.producto_id=%s AND o.tipo='AGREGADO' AND o.activo AND i.activo
                 AND p.activo AND c.activa
                 AND o.costo_adicional>0 AND o.cantidad_requerida>0
                 AND lower(c.nombre)<>'dips extra'
                 AND EXISTS(SELECT 1 FROM receta_producto(p.id,%s) r
                            WHERE r.ingrediente_id=o.ingrediente_id)
               ORDER BY o.ingrediente_id FOR SHARE OF o,p,c""",
            (producto_id, variante),
        )

    async def validar_stock_recetas(self, items: list[dict]) -> None:
        """Suma demanda en unidades de inventario y serializa la lectura de saldos."""
        demanda = {}
        for item in items:
            receta = item["receta_snapshot"]
            if not receta:
                raise ReglaDeNegocio("El producto no tiene una receta valida")
            nombres = await self.nombres_ingredientes([r["ingrediente_id"] for r in receta])
            omitidos = ingredientes_omitidos_de_aclaraciones(item.get("aclaraciones"))
            for fila in receta:
                ingrediente_id = fila["ingrediente_id"]
                if nombres.get(ingrediente_id, "").casefold() in omitidos:
                    continue
                demanda[ingrediente_id] = demanda.get(ingrediente_id, Decimal("0")) + (
                    Decimal(str(fila["cantidad_requerida"])) * item["cantidad"]
                )
        for ingrediente_id, cantidad in sorted(demanda.items()):
            saldo = await self.uow.uno(
                "SELECT cantidad_actual,activo FROM ingrediente WHERE id=%s FOR UPDATE",
                (ingrediente_id,),
            )
            if saldo is None or not saldo["activo"]:
                raise ReglaDeNegocio("La receta contiene ingredientes inactivos o inexistentes")
            if cantidad > saldo["cantidad_actual"]:
                raise StockInsuficiente(
                    "No hay stock suficiente para la cantidad pedida. Revisá el carrito.",
                    {"ingrediente_id": ingrediente_id},
                )

    async def cliente_para_usuario(self, usuario_id: int) -> int | None:
        """Devuelve el cliente activo vinculado a una cuenta de usuario activa."""
        return await self.uow.valor(
            """
            SELECT c.id FROM cliente c JOIN usuario u ON u.id = c.usuario_id
            WHERE c.usuario_id = %s AND c.estado = 'ACTIVO' AND u.estado = 'ACTIVO'
            """,
            (usuario_id,),
        )

    async def direccion_valida(self, cliente_id: int, direccion_id: int) -> bool:
        """Indica si la dirección es del cliente, está activa y su zona tiene cobertura."""
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
        """Crea una dirección del cliente si la localidad es una zona activa.

        Devuelve el id creado, o ``None`` si la localidad no tiene cobertura.
        """
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
        """Devuelve los productos pedidos con su disponibilidad y la de cada variante.

        Toma un lock compartido (FOR SHARE) para que el catálogo no cambie durante la compra.
        """
        return await self.uow.todos(
            """
            SELECT p.id, p.nombre, p.precio_base, p.activo,
                   COALESCE((SELECT jsonb_agg(v || jsonb_build_object(
                       'disponible', variante_producto_disponible(p.id, v->>'nombre')) ORDER BY n)
                       FROM jsonb_array_elements(p.variantes) WITH ORDINALITY x(v,n)),
                       '[]'::jsonb) AS variantes,
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
        """Inserta el pedido PENDIENTE con sus ítems y su primer evento de historial.

        Cada ítem guarda una copia (snapshot) de la receta vigente para descontar stock luego.
        """
        subtotal = sum(
            (
                (
                    Decimal(str(item["precio_unitario"]))
                    + Decimal(str(item.get("costo_opciones", 0)))
                )
                * item["cantidad"]
                for item in items
            ),
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
        # Inserta cada línea congelando precio, nombre y receta del momento de la compra.
        for item in items:
            costo_opciones = Decimal(str(item.get("costo_opciones", 0)))
            item_subtotal = (Decimal(str(item["precio_unitario"])) + costo_opciones) * item[
                "cantidad"
            ]
            receta = item.get("receta_snapshot")
            if receta is None:
                receta = await self.uow.todos(
                    "SELECT ingrediente_id, cantidad_requerida, es_base "
                    "FROM receta_producto(%s, %s) ORDER BY ingrediente_id",
                    (item["producto_id"], item.get("variante")),
                )
            receta_snapshot = [
                {**ingrediente, "cantidad_requerida": str(ingrediente["cantidad_requerida"])}
                for ingrediente in receta
            ]
            await self.uow.ejecutar(
                """
                INSERT INTO pedido_item
                    (pedido_id, producto_id, nombre_producto, cantidad,
                     precio_unitario, costo_opciones, subtotal, aclaraciones,
                     variante, receta_snapshot,extras_snapshot)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,%s::jsonb)
                """,
                (
                    pedido_id,
                    item["producto_id"],
                    item["nombre_producto"],
                    item["cantidad"],
                    item["precio_unitario"],
                    costo_opciones,
                    item_subtotal,
                    item["aclaraciones"],
                    item.get("variante"),
                    json.dumps(receta_snapshot),
                    json.dumps(item.get("extras_snapshot", [])),
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

    async def items_edicion(self, pedido_id: int) -> list[dict]:
        """Devuelve las líneas actuales del pedido para editarlas."""
        return await self._items(pedido_id)

    async def items_retirados(self, pedido_id: int) -> list[dict]:
        """Devuelve las líneas retiradas para su recuperación validada por el caso de uso."""
        return await self._items(pedido_id, retirados=True)

    async def receta_edicion(self, producto_id: int, variante: str | None) -> list[dict]:
        """Devuelve la receta vigente de un producto y variante, con cantidades como texto."""
        filas = await self.uow.todos(
            "SELECT ingrediente_id,cantidad_requerida,es_base FROM receta_producto(%s,%s) "
            "ORDER BY ingrediente_id", (producto_id, variante),
        )
        return [{**fila, "cantidad_requerida": str(fila["cantidad_requerida"])} for fila in filas]

    async def nombres_ingredientes(self, ids: list[int]) -> dict[int, str]:
        """Devuelve el nombre de cada ingrediente indicado, por id."""
        filas = await self.uow.todos("SELECT id,nombre FROM ingrediente WHERE id=ANY(%s)", (ids,))
        return {fila["id"]: fila["nombre"] for fila in filas}

    async def guardar_items(
        self, pedido_id: int, items: list[dict], subtotal: Decimal, total: Decimal,
        *, usuario_id: int | None, origen: str, anteriores: list[dict],
    ) -> dict:
        """Guarda una nueva composición de ítems, sube la versión y registra el historial.

        Si la composición no cambió, no escribe nada y devuelve el detalle actual.
        """
        if items == anteriores:
            return await self.detalle(pedido_id)
        await self._guardar_composicion(pedido_id, items)
        await self.uow.ejecutar(
            "UPDATE pedido SET subtotal=%s,total=%s,version=version+1 WHERE id=%s",
            (subtotal, total, pedido_id),
        )
        cambios = {"items": {"anterior": anteriores, "nuevo": items}}
        await self.uow.ejecutar(
            "INSERT INTO pedido_estado_historial(pedido_id,estado_anterior,estado_nuevo,usuario_id,"
            "observacion,origen,version,cambios) SELECT id,estado,estado,%s,'Edicion de productos',"
            "%s,version,%s::jsonb FROM pedido WHERE id=%s",
            (usuario_id, origen, json.dumps(cambios, default=str), pedido_id),
        )
        return await self.detalle(pedido_id)

    async def _guardar_composicion(self, pedido_id: int, items: list[dict]) -> None:
        """Sincroniza líneas mediante baja lógica, actualización o alta."""
        conservados = [item["id"] for item in items if item.get("id") is not None]
        await self.uow.ejecutar(
            "UPDATE pedido_item SET eliminado_en=now() WHERE pedido_id=%s "
            "AND eliminado_en IS NULL AND NOT (id=ANY(%s::bigint[]))",
            (pedido_id, conservados),
        )
        # Las líneas existentes solo cambian cantidad y aclaraciones; las nuevas se insertan.
        for item in items:
            if item.get("id") is not None:
                await self.uow.ejecutar(
                    "UPDATE pedido_item SET cantidad=%s,aclaraciones=%s,subtotal=%s,"
                    "costo_opciones=%s,receta_snapshot=%s::jsonb,extras_snapshot=%s::jsonb,"
                    "eliminado_en=NULL "
                    "WHERE id=%s AND pedido_id=%s",
                    (
                        item["cantidad"],
                        item["aclaraciones"],
                        item["subtotal"],
                        item["costo_opciones"],
                        json.dumps(item["receta_snapshot"]),
                        json.dumps(item.get("extras", [])),
                        item["id"],
                        pedido_id,
                    ),
                )
            else:
                item["id"] = await self.uow.valor(
                    "INSERT INTO pedido_item(pedido_id,producto_id,nombre_producto,cantidad,"
                    "precio_unitario,costo_opciones,subtotal,aclaraciones,"
                    "variante,receta_snapshot,extras_snapshot) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb) RETURNING id",
                    (
                        pedido_id,
                        item["producto_id"],
                        item["nombre_producto"],
                        item["cantidad"],
                        item["precio_unitario"],
                        item["costo_opciones"],
                        item["subtotal"],
                        item["aclaraciones"],
                        item.get("variante"),
                        json.dumps(item["receta_snapshot"]),
                        json.dumps(item.get("extras", [])),
                    ),
                )

    async def guardar_edicion(
        self, pedido_id: int, nuevos: dict, *, usuario_id: int | None,
        origen: str, anterior: dict, anteriores: list[dict],
    ) -> dict:
        """Guarda una edición completa (operación e ítems) con versión e historial.

        También sincroniza el borrador de WhatsApp asociado al pedido, si existe.
        """
        campos = ("tipo_entrega", "direccion_id", "metodo_pago_acordado", "observaciones",
                  "subtotal", "costo_envio", "total")
        # Solo se registran en el historial los campos que realmente cambiaron.
        cambios = {
            campo: {"anterior": anterior.get(campo), "nuevo": nuevos.get(campo)}
            for campo in campos if anterior.get(campo) != nuevos.get(campo)
        }
        if nuevos["items"] != anteriores:
            await self._guardar_composicion(pedido_id, nuevos["items"])
            cambios["items"] = {"anterior": anteriores, "nuevo": nuevos["items"]}
        if not cambios:
            return await self.detalle(pedido_id)
        await self.uow.ejecutar(
            "UPDATE pedido SET tipo_entrega=%s,direccion_id=%s,metodo_pago_acordado=%s,"
            "observaciones=%s,subtotal=%s,costo_envio=%s,total=%s,version=version+1 WHERE id=%s",
            tuple(nuevos[campo] for campo in campos) + (pedido_id,),
        )
        await self.uow.ejecutar(
            "INSERT INTO pedido_estado_historial(pedido_id,estado_anterior,estado_nuevo,"
            "usuario_id,observacion,origen,version,cambios) "
            "SELECT id,estado,estado,%s,'Edicion conjunta del pedido',%s,version,%s::jsonb "
            "FROM pedido WHERE id=%s",
            (usuario_id, origen, json.dumps(cambios, default=str), pedido_id),
        )
        # Mantiene alineado el borrador del chat con la modalidad, el pago y la dirección.
        await self.uow.ejecutar(
            "UPDATE whatsapp_borrador SET tipo_entrega=%s,metodo_pago=%s,"
            "direccion=(SELECT to_jsonb(d) FROM direccion d WHERE d.id=%s),version=version+1 "
            "WHERE pedido_id=%s",
            (nuevos["tipo_entrega"], nuevos["metodo_pago_acordado"],
             nuevos["direccion_id"], pedido_id),
        )
        return await self.detalle(pedido_id)

    async def costo_direccion(self, direccion_id: int) -> Decimal | None:
        """Devuelve el costo de envío de la zona de una dirección activa."""
        return await self.uow.valor(
            "SELECT z.costo_envio FROM direccion d JOIN zona_cobertura z ON z.id=d.zona_id "
            "WHERE d.id=%s AND d.activa AND z.activa FOR SHARE OF z,d",
            (direccion_id,),
        )

    async def costo_localidad(self, localidad: str) -> Decimal | None:
        """Devuelve el costo de envío de una localidad con cobertura activa."""
        return await self.uow.valor(
            "SELECT costo_envio FROM zona_cobertura "
            "WHERE lower(nombre)=lower(%s) AND activa FOR SHARE",
            (localidad,),
        )

    async def neto_cobrado(self, pedido_id: int) -> Decimal:
        """Devuelve lo cobrado neto del pedido: cobros conciliados menos devoluciones."""
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
        """Persiste el cambio operativo del pedido, su historial y el borrador de chat."""
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
        finalizados_hoy: bool = False,
    ) -> list[dict]:
        pedidos = await self._filas_listado(
            cliente_id=cliente_id, repartidor_id=repartidor_id, q=q, estado=estado,
            activos=activos, finalizados_hoy=finalizados_hoy,
        )
        await self._completar(pedidos)
        return pedidos

    async def revision(self, **filtros) -> str:
        """Huella privada del listado y sus relaciones, en una sola consulta SQL."""
        filas = await self._filas_listado(**filtros, con_revision=True)
        return hashlib.sha256(
            json.dumps(filas, sort_keys=True, default=str).encode()
        ).hexdigest()

    async def _filas_listado(
        self, *, cliente_id: int | None, repartidor_id: int | None = None,
        q: str | None = None, estado: str | None = None, activos: bool | None = None,
        finalizados_hoy: bool = False, con_revision: bool = False,
    ) -> list[dict]:
        """Lista pedidos con sus relaciones, aplicando filtros opcionales.

        Filtra por cliente, estado, activos, texto libre y, para repartidores, solo los pedidos de
        sus viajes abiertos.
        """
        # SQL constante: las entradas del usuario siguen siendo parámetros.
        revision = """
            ,(SELECT md5(COALESCE(jsonb_agg(to_jsonb(pg) ORDER BY pg.id)::text,'[]'))
                FROM pago pg WHERE pg.pedido_id=p.id) AS revision_pagos
            ,(SELECT md5(COALESCE(jsonb_agg(to_jsonb(e) ||
                    jsonb_build_object('viaje',to_jsonb(v)) ORDER BY e.id)::text,'[]'))
                FROM envio e LEFT JOIN viaje v ON v.id=e.viaje_id
                WHERE e.pedido_id=p.id) AS revision_envios
            ,(SELECT md5(COALESCE(jsonb_agg(to_jsonb(i) ORDER BY i.id)::text,'[]'))
                FROM pedido_item i WHERE i.pedido_id=p.id) AS revision_items
            ,(SELECT md5(COALESCE(jsonb_agg(to_jsonb(h) ORDER BY h.id)::text,'[]'))
                FROM pedido_estado_historial h WHERE h.pedido_id=p.id) AS revision_historial
            ,(SELECT md5(to_jsonb(d)::text) FROM direccion d
                WHERE d.id=p.direccion_id) AS revision_direccion
        """ if con_revision else ""
        texto, digitos = terminos_busqueda(q)
        # Cada filtro es opcional: un parámetro NULL desactiva su condición.
        pedidos = await self.uow.todos(
            f"""
            SELECT p.id, p.numero, p.cliente_id,
                   COALESCE(NULLIF(concat_ws(' ', u.nombre, u.apellido), ''), c.nombre) AS cliente,
                   p.tipo_entrega, p.direccion_id, p.estado, p.subtotal,
                   p.costo_envio, p.total, p.observaciones, p.creado_en,
                   p.version,p.metodo_pago_acordado,p.confirmado_en,p.preparacion_en,
                   p.listo_en,p.entregado_en,p.cancelado_en,c.telefono_whatsapp AS telefono
                   {revision}
            FROM pedido p
            JOIN cliente c ON c.id = p.cliente_id
            LEFT JOIN usuario u ON u.id = c.usuario_id
            WHERE (%s::bigint IS NULL OR p.cliente_id = %s)
              AND (%s::text IS NULL OR p.estado=%s)
              AND (%s::boolean IS NULL OR CASE WHEN %s THEN
                    p.estado NOT IN ('ENTREGADO','CANCELADO') OR (
                        p.estado='ENTREGADO' AND p.total > (
                            SELECT COALESCE(sum(CASE WHEN pg.tipo='COBRO'
                                THEN pg.monto ELSE -pg.monto END),0)
                            FROM pago pg WHERE pg.pedido_id=p.id AND pg.estado='CONCILIADO'
                        )
                    )
                  ELSE p.estado IN ('ENTREGADO','CANCELADO') END)
              AND (%s::text IS NULL OR lower(translate(concat_ws(' ',p.numero,c.nombre,
                  u.nombre,u.apellido,c.telefono_whatsapp,c.telefono_contacto,p.observaciones),
                  '{_CON_TILDE}','{_SIN_TILDE}')) LIKE '%%' || %s || '%%' ESCAPE '\\'
                  OR c.telefono_whatsapp LIKE '%%' || %s::text || '%%'
                  OR c.telefono_contacto LIKE '%%' || %s::text || '%%')
              AND (NOT %s OR (
                  p.estado IN ('ENTREGADO','CANCELADO') AND
                  (CASE WHEN p.estado='ENTREGADO' THEN p.entregado_en ELSE p.cancelado_en END
                      AT TIME ZONE 'America/Argentina/Buenos_Aires')::date =
                  (now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date
              ))
              AND (%s::bigint IS NULL OR EXISTS (
                  SELECT 1 FROM envio e JOIN viaje v ON v.id = e.viaje_id
                  WHERE e.pedido_id = p.id AND v.repartidor_id = %s
                    AND v.estado IN ('PLANIFICADO', 'EN_RUTA')
                    AND e.estado IN ('ASIGNADO', 'EN_CAMINO')
              ))
            ORDER BY CASE WHEN %s THEN
                CASE WHEN p.estado='ENTREGADO' THEN p.entregado_en ELSE p.cancelado_en END
                END DESC NULLS LAST, p.creado_en DESC, p.id DESC
            """,
            (
                cliente_id,
                cliente_id,
                estado,
                estado,
                activos,
                activos,
                texto,
                texto,
                digitos,
                digitos,
                finalizados_hoy,
                repartidor_id,
                repartidor_id,
                finalizados_hoy,
            ),
        )
        return pedidos

    async def detalle(self, pedido_id: int) -> dict:
        """Devuelve el pedido completo con sus relaciones, o ``None`` si no existe."""
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
        # Inicializa las colecciones y luego reparte cada consulta en bloque por pedido.
        for pedido in pedidos:
            pedido.update(items=[], historial=[], pagos=[], direccion=None, envio=None)
        items = await self.uow.todos(
            "SELECT id,pedido_id,producto_id,nombre_producto,cantidad,precio_unitario,"
            "costo_opciones,subtotal,aclaraciones,variante,receta_snapshot,"
            "extras_snapshot AS extras "
            "FROM pedido_item WHERE pedido_id=ANY(%s) "
            "AND eliminado_en IS NULL ORDER BY id",
            (ids,),
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
        # Calcula lo cobrado neto y el saldo pendiente de cada pedido.
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

    async def item_tiene_opciones(self, item_id: int) -> bool:
        """Detecta personalizaciones conservadas, aunque la línea esté retirada."""
        return bool(await self.uow.valor(
            "SELECT EXISTS (SELECT 1 FROM pedido_item_opcion WHERE pedido_item_id=%s)",
            (item_id,),
        ))

    async def _items(self, pedido_id: int, *, retirados: bool = False) -> list[dict]:
        """Devuelve líneas vigentes o retiradas con su precio y receta congelados."""
        return await self.uow.todos(
            """
            SELECT id, producto_id, nombre_producto, cantidad, precio_unitario,
                   costo_opciones, subtotal, aclaraciones, variante, receta_snapshot,
                   extras_snapshot AS extras
            FROM pedido_item WHERE pedido_id = %s
              AND (eliminado_en IS NOT NULL) = %s ORDER BY id
            """,
            (pedido_id, retirados),
        )

    async def obtener(self, pedido_id: int, *, bloquear: bool = False) -> dict | None:
        """Devuelve la fila del pedido; con ``bloquear`` la bloquea y agrega indicadores.

        Los indicadores (puede preparar, asignado, salida y entrega reales) se calculan después del
        lock para leer el estado vigente de pagos y envíos.
        """
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
                       (p.total <= (
                           SELECT COALESCE(sum(CASE WHEN tipo='COBRO' THEN monto ELSE -monto END),0)
                           FROM pago WHERE pedido_id=p.id AND estado='CONCILIADO'
                       )) AS pago_completo,
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
        """Devuelve las líneas con los datos que necesita Stock para consumir insumos."""
        return await self.uow.todos(
            "SELECT producto_id, cantidad, aclaraciones, variante, receta_snapshot "
            "FROM pedido_item "
            "WHERE pedido_id = %s AND eliminado_en IS NULL ORDER BY id",
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
        """Actualiza el estado y sus marcas de tiempo, y registra el historial."""
        anterior = await self.uow.valor("SELECT estado FROM pedido WHERE id = %s", (pedido_id,))
        # Cada estado fija su marca de tiempo; la cancelación guarda además el motivo.
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
