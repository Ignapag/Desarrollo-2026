"""Elecciones de conversación explícitas y acotadas a los pedidos del remitente."""

import re
import unicodedata


def _normalizar(texto):
    """Normaliza el texto del cliente: minúsculas, sin tildes, espacios simples y sin signos
    finales.
    """
    return " ".join("".join(
        c for c in unicodedata.normalize("NFD", texto.casefold())
        if unicodedata.category(c) != "Mn"
    ).split()).strip(" .!¡?¿")


def elegir_conversacion(texto, opciones):
    """Elige una conversación entre las opciones según ordinal, número de opción, número de pedido o
    «el de <producto>»; devuelve None si la elección es ambigua.
    """
    texto = _normalizar(texto)
    # Ordinales explícitos: las opciones ya vienen ordenadas de la más reciente a la más antigua.
    ordinales = {
        "el ultimo": 0, "el ultimo pedido": 0, "el mas reciente": 0,
        "el primero": 0, "el primer pedido": 0,
        "el segundo": 1, "el tercero": 2, "el cuarto": 3,
    }
    indice = ordinales.get(texto)
    if indice is not None:
        return opciones[indice] if indice < len(opciones) else None
    # Número de opción del listado mostrado (1, 2, ...).
    if texto.isdecimal() and 1 <= int(texto) <= len(opciones):
        return opciones[int(texto) - 1]
    # Número de pedido explícito: solo vale si coincide con un único pedido.
    numero = re.fullmatch(r"(?:el\s+)?(?:pedido\s*)?#?\s*([0-9]{1,10})", texto)
    if numero:
        valor = int(numero[1])
        por_numero = [o for o in opciones if o.get("numero") == valor]
        if len(por_numero) == 1:
            return por_numero[0]
        return None
    # Referencia por producto: debe identificar una única conversación.
    if texto.startswith("el de "):
        nombre = re.sub(r"^(?:la|las|los|el)\s+", "", texto[6:])
        coincidencias = [o for o in opciones if nombre and nombre in _normalizar(o["descripcion"])]
        if len(coincidencias) == 1:
            return coincidencias[0]
    return None


def respuesta_cortesia(texto):
    """Responde saludos, agradecimientos y despedidas sin interpretar el mensaje; None si no es
    cortesía.
    """
    texto = _normalizar(texto)
    if texto in {"hola", "buenas", "buen dia", "buenos dias", "buenas tardes", "buenas noches"}:
        return "👋 ¡Hola! ¿En qué te ayudo con tu pedido? 🍔"
    if texto in {"gracias", "muchas gracias", "perfecto gracias", "dale gracias"}:
        return "💚 ¡De nada! Si necesitás algo más con tu pedido, escribime por acá."
    if texto in {"chau", "hasta luego", "nos vemos"}:
        return "👋 ¡Hasta luego! Gracias por elegir Monu Burger. 🍔"
    return None


def pregunta_pedido(opciones):
    """Arma la pregunta para que el cliente elija sobre qué pedido quiere conversar."""
    lineas = ["💬 Tengo más de una compra para seguir. ¿Sobre cuál querés hablar?"]
    if len(opciones) == 1:
        lineas = ["💬 El pedido anterior ya no está activo. ¿Querés hablar de esta compra?"]
    for indice, opcion in enumerate(opciones, 1):
        titulo = "Pedido" if opcion.get("numero") else "Pedido por completar"
        lineas.append(f"{indice}. *{titulo}* · {opcion['descripcion'][:160]}")
    lineas.append("Podés decirme «el último», «el de Cheese» o elegir una opción. 😊")
    return "\n".join(lineas)
