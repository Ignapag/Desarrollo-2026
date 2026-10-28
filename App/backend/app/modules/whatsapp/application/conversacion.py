"""Continuidad del chat sin inferir autorización sobre una compra ambigua."""

from app.modules.whatsapp.domain.conversacion import (
    elegir_conversacion,
    pregunta_pedido,
    respuesta_cortesia,
)
from app.modules.whatsapp.domain.memoria import pregunta_actual
from app.modules.whatsapp.domain.mensajes import (
    es_inicio_web,
    hash_referencia,
    huella_inicio,
    numeros_pedido_en,
    referencias_en,
    sin_referencias,
    sin_selector_pedido,
    tiene_token_referencia,
)

BIENVENIDA = (
    "👋 ¡Hola! Soy el asistente de Monu Burger. 🍔\n"
    "Podés preguntarme por tu pedido o contarme qué necesitás cambiar. "
    "Para hacer una compra nueva, armá tu carrito en la web y enviá el resumen "
    "desde el WhatsApp que completaste en el formulario."
)


async def _retomar(repo, entrada, sesion):
    """Recupera el mensaje original que quedó pendiente de elegir pedido y lo reemplaza en la
    entrada, solo si es del mismo teléfono.
    """
    original = await repo.entrada(sesion["solicitud_id"])
    if original and original["telefono"] == entrada["telefono"]:
        entrada.update(
            texto=original["texto"], media_id=original["media_id"],
            _solicitud_id=original["id"], _sesion_version=sesion["version"],
        )


async def resolver_conversacion(repo, entrada, bloquear=False):
    """Determina sobre qué conversación (borrador o pedido) habla el mensaje. Devuelve la
    conversación elegida y, si no hay una, el texto de respuesta para el cliente (bienvenida,
    cortesía o pregunta de selección).
    """
    telefono = entrada["telefono"]
    sesion = await repo.sesion(telefono, bloquear)
    texto = entrada["texto"]
    # Saludos y agradecimientos se responden sin abrir ninguna conversación.
    cortesia = respuesta_cortesia(texto) if not entrada["media_id"] else None
    if cortesia:
        return None, cortesia
    kwargs = {"bloquear": bloquear, "nombre_remitente": entrada.get("nombre_remitente")}
    # Mensaje inicial de la web: se vincula a su borrador por la huella del texto.
    if es_inicio_web(texto):
        b = await repo.conversacion(telefono, inicio_hash=huella_inicio(telefono, texto), **kwargs)
        return b, None if b else BIENVENIDA
    # Selección explícita por número de pedido o referencia; más de una es ambigua.
    numeros, referencias = numeros_pedido_en(texto), referencias_en(texto)
    if len(numeros) > 1 or len(referencias) > 1:
        return None, "💬 Decime un solo pedido para ayudarte sin mezclar tus compras."
    if numeros:
        b = await repo.conversacion(telefono, numero_pedido=numeros.pop(), **kwargs)
        # Si el cliente solo eligió el pedido pendiente, se retoma su mensaje original.
        if (
            b and sesion and sesion["solicitud_id"]
            and b["referencia_hash"] in sesion["opciones"]
            and not sin_selector_pedido(sin_referencias(texto)).strip(" .!¡?¿")
            and not entrada["media_id"]
        ):
            await _retomar(repo, entrada, sesion)
        return b, None if b else (
            "💬 No encuentro ese pedido en este WhatsApp. ¿Revisamos el número?"
        )
    if referencias:
        b = await repo.conversacion(telefono, hash_referencia(referencias.pop()), **kwargs)
        return b, None if b else BIENVENIDA
    # Una referencia mal formada no habilita acceso a ninguna compra.
    if tiene_token_referencia(texto):
        return None, BIENVENIDA
    # Sin selector explícito: se usan las conversaciones activas del teléfono.
    opciones = await repo.conversaciones(telefono)
    if not opciones:
        return None, BIENVENIDA
    por_ref = {o["referencia_hash"]: o for o in opciones}
    foco = None
    # Si la conversación en foco espera una respuesta, el mensaje le pertenece.
    if sesion and sesion["referencia_hash"] in por_ref:
        foco = await repo.conversacion(telefono, sesion["referencia_hash"], **kwargs)
        if foco and pregunta_actual(foco):
            return foco, None
    # Elección libre del tipo «el último» o «el de Cheese».
    if not (sesion and sesion["solicitud_id"]) and texto.strip().casefold().startswith("el "):
        elegida = elegir_conversacion(texto, opciones)
        if elegida:
            entrada["_eleccion"] = True
            return await repo.conversacion(telefono, elegida["referencia_hash"], **kwargs), None
    if foco:
        return foco, None
    refs = list(por_ref)
    # Respuesta a una pregunta de selección previa.
    if sesion and sesion["solicitud_id"]:
        # Nunca reinterpretar «1» contra una lista que cambió desde la pregunta.
        if refs == sesion["opciones"]:
            elegida = elegir_conversacion(texto, opciones) if not entrada["media_id"] else None
            if elegida:
                await _retomar(repo, entrada, sesion)
                if entrada.get("_solicitud_id"):
                    return await repo.conversacion(
                        telefono, elegida["referencia_hash"], **kwargs
                    ), None
    elif not sesion and len(opciones) == 1:
        return await repo.conversacion(telefono, refs[0], **kwargs), None
    # No se pudo decidir: se registra la pregunta y se ofrece el listado.
    entrada["_pregunta"] = {
        "solicitud_id": (
            sesion["solicitud_id"] if sesion and sesion["solicitud_id"] else entrada["id"]
        ),
        "opciones": refs,
    }
    return None, pregunta_pedido(opciones)
