"""Memoria semántica: nunca copia texto libre, contactos ni direcciones al historial de IA."""

PREGUNTAS = {
    "direccion": "📍 Claro, ¿a qué dirección querés recibirlo? Pasame calle, número y localidad.",
    "numero": "📍 ¿Cuál es el número de la dirección?",
    "localidad": "📍 ¿En qué localidad es: Ensenada o Punta Lara?",
    "producto": "🍔 ¿Cuál de los productos de tu pedido querés modificar?",
    "variante": "🍔 ¿Qué variante preferís para esa hamburguesa?",
    "cantidad": "🍔 ¿Cuántas unidades querés? Respondé cantidad N (1 a 50).",
    "personalizacion": "🍔 Indicá Sin ingrediente o receta original.",
    "entrega": "🛍️ ¿Lo retirás en el local o preferís delivery? 🛵",
    "pago": "💵 ¿Preferís efectivo o transferencia? 🏦",
    "consulta": "💬 Contame un poco más qué necesitás con tu pedido y te ayudo.",
}
CAMPOS_DATOS = {"direccion", "numero", "localidad", "referencias", "tipo_entrega", "metodo_pago"}


def pregunta_actual(b):
    pregunta = b.get("contexto_chat", {}).get("pregunta")
    if pregunta in PREGUNTAS:
        return pregunta
    if (b.get("propuesta") or {}).get("tipo") == "ACLARACION":
        return "producto"
    return None


def resumir_turno(accion, b, ingredientes_permitidos):
    """La memoria describe intenciones y preguntas, sin serializar argumentos privados."""
    nombre = accion.get("accion")
    args = accion.get("argumentos") or {}
    cliente = "Consultó sobre su pedido."
    if nombre == "preguntar":
        campo = args.get("campo")
        cliente = (
            "Quiere completar o cambiar la dirección."
            if campo in {"direccion", "numero", "localidad"}
            else "Pidió ayuda para completar su pedido."
        )
    elif nombre == "datos":
        campos = sorted(set(args) & CAMPOS_DATOS)
        cliente = "Aportó datos del pedido: " + ", ".join(campos) + "."
    elif nombre == "editar_pedido":
        cliente = "Pidió varios cambios del pedido en una misma solicitud."
    elif nombre == "quitar_ingrediente":
        ingrediente = str(args.get("ingrediente", "")).casefold()
        cliente = "Pidió quitar un ingrediente."
        if ingrediente in ingredientes_permitidos:
            cliente = f"Pidió quitar {ingrediente}."
    elif nombre == "cantidad":
        cantidad = args.get("cantidad")
        if type(cantidad) is int and 1 <= cantidad <= 50:
            cliente = f"Pidió cambiar la cantidad a {cantidad}."
    elif nombre == "confirmar":
        cliente = "Pidió confirmar la propuesta vigente."
    elif nombre == "humano":
        cliente = "La interpretación no estuvo disponible." if accion.get(
            "motivo"
        ) == "PROVEEDOR" else "Pidió atención del personal."
    indice = args.get("item_indice")
    if type(indice) is int and 1 <= indice <= 50:
        cliente += f" Producto {indice}."
    pregunta = pregunta_actual(b)
    if accion.get("motivo") == "PROVEEDOR":
        asistente = "El asistente de IA no estaba disponible. No se aplicaron cambios."
    elif b["estado"] == "HUMANO":
        asistente = "La solicitud quedó para atención del personal, sin modificar el pedido."
    elif pregunta:
        asistente = PREGUNTAS[pregunta]
    elif (b.get("propuesta") or {}).get("tipo") in {
        "TOTAL", "COMPOSICION", "CANCELACION", "MULTIPLE",
    }:
        asistente = "Pidió confirmar expresamente el nuevo total antes de aplicar el cambio."
    else:
        asistente = "Respondió sobre el pedido y validó la operación según sus reglas."
    return {"cliente": cliente[:240], "asistente": asistente[:400]}
