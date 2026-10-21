"""Una solicitud conversacional completa produce una única edición confirmada."""

from copy import deepcopy
from decimal import Decimal

from app.errores import ErrorDominio
from app.modules.whatsapp.application.edicion_conversacional import (
    ARGUMENTOS_EDICION,
    normalizar,
    resolver_items,
)
from app.modules.whatsapp.domain.memoria import CAMPOS_DATOS, PREGUNTAS
from app.modules.whatsapp.domain.mensajes import resumen

MAX_OPERACIONES = 8
ACCIONES_PLAN = (set(ARGUMENTOS_EDICION) - {"cancelar"}) | {"datos"}
_CAMPOS_ITEM = {"id", "producto_id", "cantidad", "variante", "aclaraciones"}


def _argumentos_validos(nombre, args):
    if not isinstance(args, dict):
        return False
    campos = CAMPOS_DATOS if nombre == "datos" else ARGUMENTOS_EDICION.get(nombre, set())
    if set(args) - campos or (nombre == "datos" and not args):
        return False
    for campo, valor in args.items():
        if campo in {"cantidad", "item_indice", "catalogo_indice"}:
            if type(valor) is not int or not 1 <= valor <= 50:
                return False
        elif (not isinstance(valor, str) or len(valor) > 300
              or (not valor.strip() and campo != "aclaraciones")):
            return False
    for campo, opciones in (
        ("tipo_entrega", {"retiro", "delivery"}),
        ("metodo_pago", {"efectivo", "transferencia"}),
    ):
        if campo in args and args[campo].lower() not in opciones:
            return False
    return True


def _plan_valido(args):
    if not isinstance(args, dict) or set(args) != {"operaciones"}:
        return False
    operaciones = args["operaciones"]
    return isinstance(operaciones, list) and 1 <= len(operaciones) <= MAX_OPERACIONES and all(
        isinstance(op, dict) and set(op) == {"accion", "argumentos"}
        and isinstance(op["accion"], str) and op["accion"] in ACCIONES_PLAN
        and _argumentos_validos(op["accion"], op["argumentos"])
        for op in operaciones
    )


def _items_simples(items):
    return [{k: v for k, v in item.items() if k in _CAMPOS_ITEM} for item in items]


def _guardar(b, estado, pregunta=None, edicion=None):
    b["contexto_chat"] = {"multiple": estado, "pregunta": pregunta}
    if edicion:
        edicion["datos_presentes"] = sorted(estado["datos"])
        b["contexto_chat"]["edicion"] = edicion
    b["propuesta"] = None


def _pedir_dato(b, estado, campo):
    _guardar(b, estado, campo, {
        "accion": "datos", "argumentos": {}, "datos_presentes": sorted(estado["datos"]),
        "operacion": estado["operacion"], "solicitud_id": estado["solicitud_id"],
    })
    return PREGUNTAS[campo]


async def _cambios_datos(bot, b, estado, pedido):
    datos = estado["datos"]
    cambios = {}
    for campo, destino in (("tipo_entrega", "tipo_entrega"),
                           ("metodo_pago", "metodo_pago_acordado")):
        if campo in datos:
            cambios[destino] = datos[campo].upper()
    if cambios.get("tipo_entrega") == "RETIRO":
        # Retiro no conserva una dirección de entrega pendiente.
        return cambios, None
    if set(datos) & {"direccion", "numero", "localidad"}:
        for campo in ("direccion", "numero", "localidad"):
            if not datos.get(campo):
                return None, _pedir_dato(b, estado, campo)
        cambios["direccion_nueva"] = {
            "calle": datos["direccion"], "numero": datos["numero"],
            "localidad": datos["localidad"], "referencia": datos.get("referencias", ""),
        }
        cambios.setdefault("tipo_entrega", "DELIVERY")
    elif "referencias" in datos:
        direccion = await bot.repo.direccion_pedido(pedido)
        if not direccion:
            return None, _pedir_dato(b, estado, "direccion")
        cambios["direccion_nueva"] = {**direccion, "referencia": datos["referencias"]}
    if cambios.get("tipo_entrega", pedido["tipo_entrega"]) == "DELIVERY" and not (
        cambios.get("direccion_nueva") or pedido.get("direccion_id")
    ):
        return None, _pedir_dato(b, estado, "direccion")
    return cambios, None


def _detalle(pedido, cotizacion, cambios):
    texto = resumen({**pedido, **cotizacion})
    direccion = cambios.get("direccion_nueva")
    if direccion and cotizacion["tipo_entrega"] == "DELIVERY":
        texto += (f"\n📍 {direccion['calle']} {direccion['numero']}, {direccion['localidad']}")
        if direccion.get("referencia"):
            texto += f"\nReferencia: {direccion['referencia']}"
    metodo = cotizacion["metodo_pago_acordado"]
    texto += "\n💵 Efectivo" if metodo == "EFECTIVO" else "\n🏦 Transferencia"
    return texto


async def editar_multiples(bot, b, entrada, accion):
    pedido = await bot.repo.pedido(b["pedido_id"])
    foto = bot._foto_operacion(pedido)
    nombre = accion.get("accion")
    args = accion.get("argumentos") or {}
    chat = b.get("contexto_chat") or {}
    estado = deepcopy(chat.get("multiple"))
    propuesta = b.get("propuesta") or {}
    confirmar = nombre == "confirmar"
    if confirmar:
        if normalizar(entrada["texto"]) not in {
            "confirmar", "confirmo", "confirmar pedido", "confirmo pedido",
        }:
            return "💬 Respondé *confirmar* para aceptar todos los cambios."
        if propuesta.get("tipo") != "MULTIPLE":
            return (
                "💬 Primero completá el dato pendiente; "
                "todavía no hay una propuesta para confirmar."
            )
        if (propuesta.get("version") != b["version"] or propuesta.get("operacion") != foto):
            bot._limpiar_solicitud(b)
            return "💬 Tu pedido cambió. No apliqué los cambios; revisemos una nueva propuesta."
        items, cambios = propuesta["items"], propuesta["cambios"]
    else:
        completar = False
        if nombre == "editar_pedido":
            if not _plan_valido(args):
                bot._limpiar_solicitud(b)
                return "💬 No pude interpretar todos los cambios. No apliqué ninguno; reformulalos."
            operaciones = deepcopy(args["operaciones"])
            datos = {}
            for op in operaciones:
                if op["accion"] == "datos":
                    datos.update(op["argumentos"])
            estado = {
                "operaciones": [op for op in operaciones if op["accion"] != "datos"],
                "cantidad_operaciones": len(operaciones), "indice": 0,
                "items": _items_simples(pedido["items"]), "datos": datos,
                "originales": [i["id"] for i in pedido["items"]], "operacion": foto,
                "lineas": [i["id"] for i in pedido["items"]],
                "solicitud_id": entrada.get("_solicitud_id", entrada["id"]),
            }
        elif estado:
            if estado["operacion"] != foto:
                bot._limpiar_solicitud(b)
                return "💬 Tu pedido cambió. No apliqué nada; pedí nuevamente los cambios."
            if nombre in {"completar_edicion", "datos"}:
                datos = {k: v for k, v in args.items() if k in CAMPOS_DATOS}
                item = {k: v for k, v in args.items() if k not in CAMPOS_DATOS}
                campos_item = set().union(*ARGUMENTOS_EDICION.values())
                activo = (chat.get("edicion") or {}).get("accion")
                if ((datos and not _argumentos_validos("datos", datos))
                        or set(item) - campos_item
                        or (item and (not activo or not _argumentos_validos(activo, item)))):
                    return "💬 No pude interpretar la aclaración. Los cambios siguen sin aplicar."
                estado["datos"].update(datos)
                completar = True
                args = item
            elif nombre in ACCIONES_PLAN - {"datos"}:
                if (estado["cantidad_operaciones"] >= MAX_OPERACIONES
                        or not _argumentos_validos(nombre, args)):
                    return "💬 No pude sumar ese cambio al plan. No apliqué los cambios."
                estado["operaciones"].append({"accion": nombre, "argumentos": deepcopy(args)})
                estado["cantidad_operaciones"] += 1
            else:
                return "💬 Completá el dato pendiente para preparar todos los cambios."
        else:
            return "💬 No hay cambios múltiples pendientes. Contame qué querés modificar."
        b["version"] += 1
        _guardar(b, estado)
        while estado["indice"] < len(estado["operaciones"]):
            op = deepcopy(estado["operaciones"][estado["indice"]])
            pendiente = deepcopy(chat.get("edicion")) if completar else None
            if pendiente:
                op = {"accion": "completar_edicion", "argumentos": args}
                objetivo = {**pendiente["argumentos"], **args}
                nombre_original = pendiente["accion"]
            else:
                objetivo = op["argumentos"]
                nombre_original = op["accion"]
            if nombre_original != "agregar_producto":
                indice = objetivo.get("item_indice")
                if indice is None and len(estado["originales"]) == 1:
                    indice = 1
                if type(indice) is not int or not 1 <= indice <= len(estado["originales"]):
                    edicion = {"accion": nombre_original, "argumentos": objetivo,
                        "operacion": foto, "solicitud_id": estado["solicitud_id"]}
                    _guardar(b, estado, "producto", edicion)
                    listado = "\n".join(
                        f"{n}. {i['nombre_producto']}" for n, i in enumerate(pedido["items"], 1)
                    )
                    return f"🍔 ¿Qué producto querés modificar?\n{listado}\nRespondé *producto N*."
                identificador = estado["originales"][indice - 1]
                actual = next((n for n, identidad in enumerate(estado["lineas"], 1)
                    if identidad == identificador), None)
                if actual is None:
                    bot._limpiar_solicitud(b)
                    return (
                        "💬 Un cambio modifica un producto que también quitaste. "
                        "Aclará la solicitud."
                    )
                op["argumentos"]["item_indice"] = actual
                if pendiente:
                    pendiente["argumentos"]["item_indice"] = actual
            originales = {i["id"]: i for i in pedido["items"]}
            virtual = {**pedido, "items": [
                {**originales.get(i.get("id"), {}), **i} for i in estado["items"]
            ]}
            temporal = {**b, "contexto_chat": deepcopy(chat) if pendiente else {}}
            if pendiente:
                temporal["contexto_chat"]["edicion"] = pendiente
            resultado = await resolver_items(
                bot, temporal, entrada, virtual, op, permitir_vacio=True,
            )
            completar = False
            if isinstance(resultado, str):
                if temporal["estado"] == "HUMANO":
                    b["estado"] = "HUMANO"
                temporal_chat = temporal.get("contexto_chat") or {}
                edicion = temporal_chat.get("edicion")
                # El índice mostrado al cliente siempre refiere al pedido original.
                if edicion and nombre_original != "agregar_producto":
                    edicion["argumentos"]["item_indice"] = indice
                _guardar(b, estado, temporal_chat.get("pregunta"), edicion)
                if "catalogo_opciones" in temporal_chat:
                    b["contexto_chat"]["catalogo_opciones"] = temporal_chat["catalogo_opciones"]
                return resultado
            estado["items"] = resultado[0]
            if nombre_original == "quitar_producto":
                estado["lineas"].pop(actual - 1)
            elif nombre_original == "agregar_producto":
                estado["lineas"].append(None)
            estado["indice"] += 1
            chat = {}
        items = estado["items"]
        if not items:
            bot._limpiar_solicitud(b)
            return (
                "💬 Estos cambios quitarían todos los productos. "
                "Usá *cancelar pedido* para cancelarlo."
            )
        cambios, pregunta = await _cambios_datos(bot, b, estado, pedido)
        if pregunta:
            return pregunta
    try:
        cotizacion = await bot.pedidos.cotizar_edicion(pedido["id"], items=items, cambios=cambios)
    except ErrorDominio as error:
        bot._limpiar_solicitud(b)
        if "neto" in error.mensaje.lower() or "reintegro" in error.mensaje.lower():
            return await bot._derivar(b, entrada, {"accion": "humano"})
        return f"💬 No pude preparar los cambios: {error.mensaje}. Tu pedido sigue sin cambios."
    if confirmar and Decimal(propuesta["total"]) != cotizacion["total"]:
        bot._limpiar_solicitud(b)
        return (
            "💬 Cambiaron los precios o el envío. "
            "No apliqué nada; revisemos una nueva propuesta."
        )
    if not confirmar:
        b["propuesta"] = {
            "tipo": "MULTIPLE", "version": b["version"], "operacion": foto,
            "items": items, "cambios": cambios, "total": str(cotizacion["total"]),
        }
        b["contexto_chat"] = {"pregunta": None, "multiple": estado}
        return ("💰 Así quedaría tu pedido:\n\n" + _detalle(pedido, cotizacion, cambios)
            + "\n\nRespondé *confirmar* para aplicar todos los cambios juntos.")
    # Desde la primera escritura cualquier error revierte el intento completo en el worker.
    await bot.pedidos.editar_edicion(
        pedido["id"], items=items, cambios=cambios, version_esperada=pedido["version"],
        usuario_id=None, origen="WHATSAPP", total_esperado=cotizacion["total"],
    )
    await bot.repo.refrescar_operacion(b)
    if b["metodo_pago"] == "TRANSFERENCIA" and cotizacion["total"] > pedido["pagado"]:
        b["estado_pago"] = "PENDIENTE"
    b["version"] += 1
    bot._limpiar_solicitud(b)
    await bot.repo.historial(b, {"accion": "editar_pedido", "argumentos": {}},
        {"pedido_version": pedido["version"], "total": str(pedido["total"])},
        {"total": str(cotizacion["total"])}, "APLICADO")
    return "✅ Cambios guardados.\n\n" + _detalle(pedido, cotizacion, cambios)
