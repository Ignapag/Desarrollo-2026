"""Aclaraciones y propuestas del chat; Pedidos es autoridad de la edición física."""

import re
from decimal import Decimal

from app.errores import ErrorDominio
from app.modules.pedidos.domain.entidades import EstadoPedido
from app.modules.whatsapp.domain.catalogo import (
    coincidencias_productos,
    normalizar,
    pregunta_producto_valida,
)
from app.modules.whatsapp.domain.mensajes import resumen

ACCIONES_ITEMS = {
    "agregar_producto",
    "quitar_producto",
    "reemplazar_producto",
    "cambiar_variante",
    "personalizar",
    "cantidad",
    "quitar_ingrediente",
    "completar_edicion",
    "cancelar",
}
ARGUMENTOS_EDICION = {
    "agregar_producto": {"producto", "cantidad", "variante", "aclaraciones", "catalogo_indice",
                         "pregunta_producto"},
    "reemplazar_producto": {
        "producto", "cantidad", "variante", "aclaraciones", "catalogo_indice", "item_indice",
        "pregunta_producto",
    },
    "cambiar_variante": {"producto", "variante", "item_indice", "cantidad", "aclaraciones"},
    "quitar_producto": {"item_indice"},
    "cantidad": {"cantidad", "item_indice"},
    "personalizar": {"aclaraciones", "item_indice"},
    "quitar_ingrediente": {"ingrediente", "item_indice"},
    "cancelar": set(),
}
AYUDA = (
    "💬 Podés seguir sin IA con estos comandos:\n"
    "• *agregar*: muestra el catálogo, después elegí *catálogo N*.\n"
    "• *quitar producto N*, *cantidad N* o *reemplazar producto N*.\n"
    "• *variante Doble producto N* o *personalizar producto N* (opciones de la receta).\n"
    "• Datos: *retiro*, *delivery*, *efectivo*, *transferencia* o "
    "*direccion: Calle; numero: 123; localidad: Ensenada; referencias: timbre*.\n"
    "• *resumen*, *cancelar pedido* o *empleado*.\n"
    "Los cambios de importe requieren *confirmar*. No se cambia nada al mostrar opciones."
)


def comando_guiado(texto, b=None):
    """Gramática explícita: permite continuar sin presentar reglas locales como IA."""
    t = normalizar(texto)
    # Comandos fijos de consulta, confirmación, cancelación y alta.
    if t in {"ayuda", "menu", "opciones"}:
        return {"accion": "ayuda", "argumentos": {}}
    if t in {"resumen", "total", "estado"}:
        return {"accion": "consulta", "argumentos": {}}
    if t in {"confirmar", "confirmo", "confirmar pedido", "confirmo pedido"}:
        return {"accion": "confirmar", "argumentos": {}}
    if t in {"cancelar pedido", "cancelar mi pedido"}:
        return {"accion": "cancelar", "argumentos": {}}
    if t in {"agregar", "agregar producto"}:
        return {"accion": "agregar_producto", "argumentos": {}}
    # Comandos sobre un producto del pedido identificado por su posición.
    for patron, accion in (
        (r"quitar producto (\d+)", "quitar_producto"),
        (r"reemplazar producto (\d+)", "reemplazar_producto"),
        (r"personalizar producto (\d+)", "personalizar"),
    ):
        if m := re.fullmatch(patron, t):
            return {"accion": accion, "argumentos": {"item_indice": int(m[1])}}
    # Con una aclaración pendiente, cantidad y variante la completan en lugar de iniciar otra.
    pendiente = ((b or {}).get("contexto_chat") or {}).get("edicion")
    if m := re.fullmatch(r"cantidad (\d+)(?: producto (\d+))?", t):
        return {
            "accion": "completar_edicion" if pendiente else "cantidad",
            "argumentos": {"cantidad": int(m[1]), **({"item_indice": int(m[2])} if m[2] else {})},
        }
    if m := re.fullmatch(r"variante (.{1,60}?)(?: producto (\d+))?", t):
        return {
            "accion": "completar_edicion" if pendiente else "cambiar_variante",
            "argumentos": {
                "variante": m[1],
                **({"item_indice": int(m[2])} if m[2] else {}),
            },
        }
    # Respuestas cortas que solo tienen sentido para completar una edición pendiente.
    if pendiente:
        for patron, campo in (
            (r"catalogo (\d+)", "catalogo_indice"),
            (r"producto (\d+)", "item_indice"),
            (r"variante (.{1,60})", "variante"),
        ):
            if m := re.fullmatch(patron, t):
                valor = int(m[1]) if campo.endswith("indice") else m[1]
                return {"accion": "completar_edicion", "argumentos": {campo: valor}}
        if t in {"sin personalizaciones", "receta original"}:
            return {"accion": "completar_edicion", "argumentos": {"aclaraciones": ""}}
        if re.fullmatch(r"sin [\w ,áéíóúñ]+", t):
            return {"accion": "completar_edicion", "argumentos": {"aclaraciones": texto.strip()}}
    # Datos de entrega y pago, sueltos o con el formato «campo: valor; campo: valor».
    if t in {"retiro", "delivery", "efectivo", "transferencia"}:
        campo = "tipo_entrega" if t in {"retiro", "delivery"} else "metodo_pago"
        return {"accion": "datos", "argumentos": {campo: t}}
    campos = {"direccion", "numero", "localidad", "referencias", "tipo_entrega", "metodo_pago"}
    segmentos = [s.partition(":") for s in texto.split(";")]
    if segmentos and all(
        sep and normalizar(clave) in campos and valor.strip() for clave, sep, valor in segmentos
    ):
        argumentos = {normalizar(k): v.strip() for k, _, v in segmentos}
        if len(argumentos) == len(segmentos):
            return {"accion": "datos", "argumentos": argumentos}
    return None


def es_modificacion(accion, b):
    """Indica si la acción solicitada modifica el pedido (productos, datos o confirmación de una
    propuesta).
    """
    nombre = accion.get("accion")
    return (
        nombre in ACCIONES_ITEMS | {"datos", "editar_pedido"}
        or (
            nombre == "preguntar"
            and (accion.get("argumentos") or {}).get("campo")
            in {"direccion", "numero", "localidad", "entrega", "pago", "producto", "variante"}
        )
        or (nombre == "confirmar" and bool(b.get("propuesta")))
    )


def requiere_personal(pedido):
    """Indica si el pedido ya avanzó a preparación o tiene repartidor, por lo que solo el personal
    puede modificarlo.
    """
    return pedido["estado"] not in {"PENDIENTE", "CONFIRMADO"} or bool(
        pedido.get("preparacion_en") or pedido.get("asignado")
    )


async def catalogo(bot):
    """Productos activos del catálogo, o lista vacía si el bot no tiene acceso al catálogo."""
    if bot.productos is None:
        return []
    return await bot.productos.listar(solo_activos=True)


def _guardar_pendiente(b, accion, argumentos, entrada, foto, campo):
    """Guarda una edición incompleta y la pregunta pendiente en el contexto del chat, invalidando
    cualquier propuesta anterior.
    """
    chat = dict(b.get("contexto_chat") or {})
    anterior = chat.get("edicion") or {}
    chat.update(
        pregunta=campo,
        edicion={
            "accion": accion,
            "argumentos": argumentos,
            "solicitud_id": anterior.get("solicitud_id", entrada["id"]),
            "operacion": foto,
        },
    )
    b["contexto_chat"] = chat
    b["propuesta"] = None
    b["version"] += 1


async def editar_productos(bot, b, entrada, accion):
    """Edita los productos del pedido desde el chat. Si la edición cambia el total, primero propone
    el nuevo importe y solo lo aplica cuando el cliente responde *confirmar*; los pedidos ya en
    preparación se derivan al personal.
    """
    pedido = await bot.repo.pedido(b["pedido_id"])
    if requiere_personal(pedido):
        return await bot._derivar(b, entrada, {"accion": "humano"})
    foto = bot._foto_operacion(pedido)
    nombre = accion.get("accion")
    propuesta = b.get("propuesta") or {}
    confirmar = nombre == "confirmar"
    # Confirmación de una propuesta previa: debe seguir vigente para la misma versión.
    if confirmar:
        if normalizar(entrada["texto"]) not in {
            "confirmar",
            "confirmo",
            "confirmar pedido",
            "confirmo pedido",
        }:
            return "💬 Para aceptar la propuesta respondé *confirmar*."
        if propuesta.get("version") != b["version"] or propuesta.get("operacion") != foto:
            bot._limpiar_solicitud(b)
            return (
                "💬 Tu pedido cambió. No apliqué la propuesta; "
                "revisá el resumen y pedí el cambio nuevamente."
            )
        # Cancelación confirmada: con pagos registrados la resuelve el personal.
        if propuesta.get("tipo") == "CANCELACION":
            if pedido["pagado"] > 0:
                return await bot._derivar(b, entrada, {"accion": "humano"})
            await bot.pedidos.cambiar_estado(
                pedido["id"],
                EstadoPedido.CANCELADO,
                usuario_id=None,
                version_esperada=pedido["version"],
                origen="WHATSAPP",
                motivo="Cancelación confirmada por el cliente",
            )
            bot._limpiar_solicitud(b)
            b["version"] += 1
            return "✅ Tu pedido fue cancelado. No se registraron cobros ni reintegros."
        nombre, args = propuesta["accion"]["accion"], dict(propuesta["accion"]["argumentos"])
        items = propuesta["items"]
    else:
        # Intención nueva: arma la composición de ítems o devuelve una aclaración.
        resultado = await resolver_items(bot, b, entrada, pedido, accion)
        if isinstance(resultado, str):
            return resultado
        items, nombre, args = resultado
    try:
        cotizacion = await bot.pedidos.cotizar_items(pedido["id"], items)
    except ErrorDominio as error:
        # Cotizar no escribe: errores de catálogo no dejan una transacción parcial.
        if "neto" in error.mensaje.lower() or "reintegro" in error.mensaje.lower():
            return await bot._derivar(b, entrada, {"accion": "humano"})
        return (
            f"💬 No pude proponer el cambio: {error.mensaje}. "
            "Tu pedido sigue sin cambios. Usá *ayuda* o *empleado*."
        )
    if confirmar and Decimal(propuesta["total"]) != cotizacion["total"]:
        bot._limpiar_solicitud(b)
        return (
            "💬 Cambiaron los precios o la disponibilidad. "
            "No apliqué el cambio; revisemos una nueva propuesta."
        )
    # Si la composición resultante es idéntica a la actual, no hay nada que guardar.
    campos = ("id", "producto_id", "cantidad", "variante", "aclaraciones")
    if [{k: i.get(k) for k in campos} for i in cotizacion["items"]] == [
        {k: i.get(k) for k in campos} for i in pedido["items"]
    ]:
        bot._limpiar_solicitud(b)
        b["version"] += 1
        detalle = (
            "sin ese ingrediente" if nombre == "quitar_ingrediente" else "con esas opciones"
        )
        return f"✅ Tu producto ya está guardado {detalle}.\n\n" + resumen(pedido)
    # Un cambio de importe no se aplica sin confirmación expresa del cliente.
    if not confirmar and cotizacion["total"] != pedido["total"]:
        b["propuesta"] = {
            "tipo": "COMPOSICION",
            "version": b["version"],
            "operacion": foto,
            "accion": {"accion": nombre, "argumentos": args},
            "items": items,
            "total": str(cotizacion["total"]),
        }
        b["contexto_chat"] = {"pregunta": None}
        return (
            "💰 Este sería el resumen y nuevo total:\n\n"
            + resumen({**pedido, **cotizacion})
            + "\n\nRespondé *confirmar* para aplicar el cambio."
        )
    # No capturar errores después de escribir: el worker revierte íntegramente el intento.
    await bot.pedidos.editar_items(
        pedido["id"],
        items=items,
        version_esperada=pedido["version"],
        usuario_id=None,
        origen="WHATSAPP",
        total_esperado=cotizacion["total"],
    )
    # Si el nuevo total supera lo ya transferido, el pago vuelve a quedar pendiente.
    if b["metodo_pago"] == "TRANSFERENCIA" and cotizacion["total"] > pedido["pagado"]:
        b["estado_pago"] = "PENDIENTE"
    b["version"] += 1
    bot._limpiar_solicitud(b)
    await bot.repo.historial(
        b,
        {"accion": nombre, "argumentos": args},
        {"pedido_version": pedido["version"], "total": str(pedido["total"])},
        {"total": str(cotizacion["total"])},
        "APLICADO",
    )
    return "✅ Cambio guardado.\n\n" + resumen(await bot.repo.pedido(pedido["id"]))


async def resolver_items(bot, b, entrada, pedido, accion, *, permitir_vacio=False):
    """Prepara una composicion sin escribir el pedido; conserva aclaraciones en b."""
    nombre = accion.get("accion")
    foto = bot._foto_operacion(pedido)
    args = dict(accion.get("argumentos") or {})
    # Una intención nueva invalida la confirmación anterior incluso si falla.
    b["propuesta"] = None
    pendiente = (b.get("contexto_chat") or {}).get("edicion") or {}
    # Completar una edición pendiente retoma la acción y los argumentos guardados.
    if nombre == "completar_edicion":
        if not pendiente:
            return AYUDA
        if pendiente["operacion"] != foto:
            bot._limpiar_solicitud(b)
            return "💬 Tu pedido cambió. Revisá el resumen antes de pedir nuevamente el cambio."
        nombre = pendiente["accion"]
        args = {**pendiente["argumentos"], **args}
    elif pendiente:
        # Una intención nueva reemplaza explícitamente la aclaración anterior.
        b["contexto_chat"].pop("edicion", None)
    # Argumentos fuera de lo permitido o preguntas inválidas de la IA se derivan al personal.
    permitidos = ARGUMENTOS_EDICION.get(nombre, set())
    if set(args) - permitidos:
        return await bot._derivar(b, entrada, {"accion": "humano"})
    pregunta_ia = args.pop("pregunta_producto", None)
    if pregunta_ia is not None and not pregunta_producto_valida(pregunta_ia):
        return await bot._derivar(b, entrada, {"accion": "humano"})
    # Copia editable de los ítems actuales del pedido.
    items = [
        {
            k: i[k]
            for k in ("id", "producto_id", "cantidad", "aclaraciones", "variante")
            if k in i
        }
        for i in pedido["items"]
    ]
    if nombre == "cancelar":
        return await _cancelar(bot, b, entrada, pedido, foto)
    # La IA pidió una aclaración sobre el producto: se guarda y se reenvía al cliente.
    if pregunta_ia:
        _guardar_pendiente(b, nombre, args, entrada, foto, "producto")
        b["contexto_chat"]["edicion"]["pregunta_producto"] = pregunta_ia.strip()
        return pregunta_ia.strip()
    # Las acciones sobre un producto existente requieren saber cuál; con uno solo se asume.
    indice = args.get("item_indice")
    if nombre != "agregar_producto":
        if indice is None and len(items) == 1:
            indice = 1
            args["item_indice"] = 1
        if type(indice) is not int or not 1 <= indice <= len(items):
            _guardar_pendiente(b, nombre, args, entrada, foto, "producto")
            listado = "\n".join(
                f"{n}. {i['nombre_producto']}" for n, i in enumerate(pedido["items"], 1)
            )
            return f"🍔 ¿Cuál producto querés modificar?\n{listado}\nRespondé *producto N*."
    if nombre == "quitar_producto":
        if len(items) == 1 and not permitir_vacio:
            return await _cancelar(bot, b, entrada, pedido, foto)
        items.pop(indice - 1)
    elif nombre in {"agregar_producto", "reemplazar_producto", "cambiar_variante"}:
        # Altas, reemplazos y cambios de variante necesitan resolver el producto del catálogo.
        productos = await catalogo(bot)
        if not productos:
            return await bot._derivar(b, entrada, {"accion": "humano"})
        producto = None
        elegido_pendiente = (
            pendiente.get("producto_elegido_id")
            if accion.get("accion") == "completar_edicion"
            and args.get("producto") == pendiente.get("argumentos", {}).get("producto")
            else None
        )
        if nombre == "cambiar_variante":
            producto = next(
                (p for p in productos if p["id"] == items[indice - 1]["producto_id"]), None
            )
            if args.get("producto") and (
                not producto or normalizar(args["producto"]) != normalizar(producto["nombre"])
            ):
                return await bot._derivar(b, entrada, {"accion": "humano"})
        elif "catalogo_indice" in args:
            opciones = (b.get("contexto_chat") or {}).get("catalogo_opciones", [])
            elegido = args["catalogo_indice"]
            if type(elegido) is int and 1 <= elegido <= len(opciones):
                producto = next(
                    (p for p in productos if p["id"] == opciones[elegido - 1]), None
                )
        elif elegido_pendiente is not None:
            producto = next((p for p in productos if p["id"] == elegido_pendiente), None)
        elif args.get("producto"):
            coincidencias = coincidencias_productos(productos, args["producto"])
            if len(coincidencias) == 1:
                producto = coincidencias[0]
            elif coincidencias:
                productos = coincidencias
        # Producto sin resolver: se ofrece el listado del catálogo para elegir.
        if producto is None:
            args.pop("catalogo_indice", None)
            _guardar_pendiente(b, nombre, args, entrada, foto, "producto")
            b["contexto_chat"]["catalogo_opciones"] = [p["id"] for p in productos[:30]]
            listado = "\n".join(f"{n}. {p['nombre']}" for n, p in enumerate(productos[:30], 1))
            return f"🍔 Elegí un producto del catálogo:\n{listado}\nRespondé *catálogo N*."
        args.pop("catalogo_indice", None)
        args["producto"] = producto["nombre"]
        # La variante debe ser una de las ofrecidas por el producto.
        variantes = producto.get("variantes") or []
        seleccion = next(
            (
                v["nombre"]
                for v in variantes
                if normalizar(v["nombre"]) == normalizar(str(args.get("variante", "")))
            ),
            None,
        )
        if variantes and seleccion is None:
            _guardar_pendiente(b, nombre, args, entrada, foto, "variante")
            b["contexto_chat"]["edicion"]["producto_elegido_id"] = producto["id"]
            return (
                f"🍔 ¿Qué variante querés para {producto['nombre']}? "
                + ", ".join(v["nombre"] for v in variantes)
                + ". Respondé *variante NOMBRE*."
            )
        # Los reemplazos conservan la cantidad anterior si el cliente no indicó otra.
        cantidad = args.get("cantidad")
        if nombre in {"reemplazar_producto", "cambiar_variante"} and cantidad is None:
            cantidad = items[indice - 1]["cantidad"]
        if type(cantidad) is not int or not 1 <= cantidad <= 50:
            _guardar_pendiente(b, nombre, args, entrada, foto, "cantidad")
            b["contexto_chat"]["edicion"]["producto_elegido_id"] = producto["id"]
            return "🍔 ¿Cuántas unidades querés agregar? Respondé *cantidad N* (1 a 50)."
        nuevo = {
            "producto_id": producto["id"],
            "cantidad": cantidad,
            "variante": seleccion,
            "aclaraciones": args.get("aclaraciones") or None,
        }
        if nombre == "agregar_producto":
            items.append(nuevo)
        elif nombre == "cambiar_variante" and seleccion == items[indice - 1].get("variante"):
            # Repetir la variante vigente no representa una nueva compra ni
            # autoriza actualizar el precio o la receta ya acordados.
            items[indice - 1]["cantidad"] = cantidad
            if "aclaraciones" in args:
                items[indice - 1]["aclaraciones"] = args["aclaraciones"] or None
        else:
            if nombre == "cambiar_variante" and "aclaraciones" not in args:
                nuevo["aclaraciones"] = items[indice - 1].get("aclaraciones")
            items[indice - 1] = nuevo
    elif nombre == "cantidad":
        cantidad = args.get("cantidad")
        if type(cantidad) is not int or not 1 <= cantidad <= 50:
            _guardar_pendiente(b, nombre, args, entrada, foto, "cantidad")
            return (
                "🍔 Respondé *cantidad N*, entre 1 y 50; para quitar usá *quitar producto N*."
            )
        items[indice - 1]["cantidad"] = cantidad
    elif nombre in {"personalizar", "quitar_ingrediente"}:
        # Quitar un ingrediente se registra como aclaración «Sin X» del ítem.
        if nombre == "quitar_ingrediente":
            ingrediente = str(args.get("ingrediente", ""))
            notas = items[indice - 1].get("aclaraciones") or ""
            args["aclaraciones"] = ", ".join(filter(None, [notas, "Sin " + ingrediente]))
        if "aclaraciones" not in args:
            _guardar_pendiente(b, nombre, args, entrada, foto, "personalizacion")
            ingredientes = await bot._ingredientes_item(pedido["items"][indice - 1])
            opciones = [
                i["nombre"] for i in ingredientes if i["nombre"].casefold() in bot.quitables
            ]
            return (
                "🍔 Podés indicar *Sin ingrediente* ("
                + ", ".join(opciones)
                + ") o *receta original* para retirar las personalizaciones."
            )
        items[indice - 1]["aclaraciones"] = args["aclaraciones"] or None
    else:
        return AYUDA
    return items, nombre, args


async def _cancelar(bot, b, entrada, pedido, foto):
    """Propone cancelar el pedido pidiendo confirmación; con pagos registrados se deriva al
    personal.
    """
    if pedido["pagado"] > 0:
        return await bot._derivar(b, entrada, {"accion": "humano"})
    b["propuesta"] = {"tipo": "CANCELACION", "version": b["version"], "operacion": foto}
    return (
        "💬 Cancelar el pedido también resuelve quitar su último producto. "
        "Respondé *confirmar* para cancelar; tu pedido sigue vigente hasta entonces."
    )
