"""Textos de WhatsApp legibles, sin referencias internas ni llamadas a proveedores."""

from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

INICIO_WEB = "¡Hola, Monu Burger! 🍔\nQuiero pedir:"
_ARGENTINA = timezone(timedelta(hours=-3))


def dinero(valor: Decimal | int | str) -> str:
    """Importe en pesos argentinos, con centavos solo cuando corresponde."""
    importe = Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    entero, centavos = f"{importe:,.2f}".split(".")
    resultado = f"$ {entero.replace(',', '.')}"
    return resultado if centavos == "00" else f"{resultado},{centavos}"


def mensaje_web(datos: dict, productos: list[dict], momento: datetime) -> str:
    """Resumen del carrito valorado con el catálogo del servidor, antes de confirmar."""
    if momento.tzinfo is None or momento.utcoffset() is None:
        raise ValueError("El momento del pedido debe incluir zona horaria")
    por_id = {producto["id"]: producto for producto in productos}
    lineas = [INICIO_WEB]
    subtotal = Decimal("0")
    for item in datos["items"]:
        producto = por_id[item["producto_id"]]
        nombre = producto["nombre"]
        precio = producto["precio_base"]
        variante = item.get("variante")
        if variante:
            seleccionada = next(
                (v for v in producto.get("variantes", []) if v["nombre"] == variante), None
            )
            if seleccionada is None:
                raise ValueError("La variante no pertenece al producto")
            precio = seleccionada["precio"]
            nombre = f"{nombre} ({variante})"
        elif producto.get("variantes"):
            nombre += " (variante a elegir)"
        importe = Decimal(str(precio)) * item["cantidad"]
        subtotal += importe
        lineas.append(f"• {item['cantidad']} × {nombre} — {dinero(importe)}")
        if item.get("aclaraciones"):
            lineas.append(f"  Nota: {item['aclaraciones']}")
    lineas.extend(["", f"*Subtotal estimado: {dinero(subtotal)}*"])
    if datos.get("tipo_entrega") == "DELIVERY":
        lineas.append("El envío se confirma aparte.")
    contacto = datos.get("contacto") or {}
    nombre = " ".join(contacto.get(campo, "").strip() for campo in ("nombre", "apellido"))
    if nombre.strip():
        lineas.extend(["", f"👤 {nombre.strip()}"])
    modalidad = datos.get("tipo_entrega")
    if modalidad in {"RETIRO", "DELIVERY"}:
        lineas.append("🛍️ Retiro en el local" if modalidad == "RETIRO" else "🛵 Delivery")
    metodo = datos.get("metodo_pago")
    if metodo in {"EFECTIVO", "TRANSFERENCIA"}:
        lineas.append(
            "💵 Pago en efectivo" if metodo == "EFECTIVO" else "🏦 Pago por transferencia"
        )
    direccion = datos.get("direccion_nueva")
    if modalidad == "DELIVERY" and direccion:
        calle = f"{direccion['calle']} {direccion.get('numero', 'S/N')}".strip()
        lineas.append(f"📍 {calle}, {direccion['localidad']}")
        if direccion.get("referencia"):
            lineas.append(f"Referencia: {direccion['referencia']}")
    fecha = momento.astimezone(_ARGENTINA).strftime("%d/%m/%Y a las %H:%M:%S")
    lineas.extend(["", f"Armé mi pedido el {fecha} (hora Argentina).", "¡Gracias! 😊"])
    mensaje = "\n".join(lineas)
    if len(mensaje) > 4096:
        raise ValueError("El resumen supera el límite de WhatsApp; reducí las aclaraciones")
    return mensaje


def resumen_pedido(pedido: dict) -> str:
    lineas = ["🍔 *Tu pedido*"]
    for item in pedido["items"]:
        lineas.append(f"• {item['cantidad']} × {item['nombre_producto']}")
        if item.get("aclaraciones"):
            lineas.append(f"  Nota: {item['aclaraciones']}")
    lineas.extend(["", f"*Total: {dinero(pedido['total'])}*"])
    lineas.append("🛍️ Retiro en el local" if pedido["tipo_entrega"] == "RETIRO" else "🛵 Delivery")
    return "\n".join(lineas)


def instrucciones_pago(metodo: str, transferencia: str, tipo_entrega: str) -> str:
    if metodo.upper() == "EFECTIVO":
        cuando = (
            "cuando retires en el local" if tipo_entrega == "RETIRO" else "cuando recibas el pedido"
        )
        return f"💵 Pagás en efectivo {cuando}. ¡Gracias!"
    if metodo.upper() == "TRANSFERENCIA":
        datos = transferencia.strip() or "Pedinos por este chat los datos para transferir."
        return (
            f"🏦 *Pago por transferencia*\n{datos}\n\n"
            "Cuando transfieras, mandanos el comprobante por acá. "
            "Un empleado lo va a revisar y te avisamos cuando el pago esté confirmado."
        )
    return "💬 Elegí cómo querés pagar: efectivo o transferencia."


def estado_pedido(pedido: dict) -> str:
    estado = pedido.get("estado", pedido.get("estado_pedido"))
    textos = {
        "PENDIENTE": "📝 Tu pedido está pendiente de confirmación.",
        "CONFIRMADO": "✅ Tu pedido está confirmado.",
        "EN_PREPARACION": "👨‍🍳 Estamos preparando tu pedido.",
        "LISTO": (
            "🛍️ ¡Tu pedido está listo! Ya podés retirarlo por el local."
            if pedido["tipo_entrega"] == "RETIRO"
            else "🍔 ¡Tu pedido está listo! Está esperando salir a reparto."
        ),
        "EN_CAMINO": (
            "🛍️ Tu pedido sigue listo para retirar por el local."
            if pedido["tipo_entrega"] == "RETIRO"
            else "🛵 ¡Tu pedido va en camino!"
        ),
        "ENTREGADO": "🙌 Tu pedido figura como entregado. ¡Que lo disfrutes!",
        "CANCELADO": "Tu pedido fue cancelado. Si necesitás ayuda, escribinos por acá. 💬",
    }
    texto = textos.get(estado, "💬 Consultanos por acá y te ayudamos con el estado de tu pedido.")
    return texto


def resultado_transferencia(numero: int, aprobar: bool) -> str:
    if aprobar:
        return (
            "✅ *Pago confirmado*\n"
            "El personal verificó tu transferencia. ¡Gracias! 🍔"
        )
    return (
        "💬 *Revisión del pago*\n"
        "No pudimos aprobar el comprobante. Revisá los datos de la transferencia y "
        "mandanos el comprobante correcto, o escribinos por acá para que te ayudemos."
    )
